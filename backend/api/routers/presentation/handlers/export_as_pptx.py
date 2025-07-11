import os
import uuid
from api.models import LogMetadata
from api.routers.presentation.mixins.fetch_presentation_assets import (
    FetchPresentationAssetsMixin,
)
from api.routers.presentation.models import (
    ExportAsRequest,
    PresentationAndPath,
)
from api.services.logging import LoggingService
from api.services.instances import temp_file_service
from api.sql_models import PresentationSqlModel
from api.utils import get_presentation_dir, sanitize_filename
from ppt_generator.pptx_presentation_creator import PptxPresentationCreator
from api.services.database import get_sql_session

# Add authentication and file manager imports
from auth.models import User, Presentation
from services.file_manager import file_manager
from services.database import get_session


class ExportAsPptxHandler(FetchPresentationAssetsMixin):

    def __init__(self, data: ExportAsRequest, current_user: User = None):
        self.data = data
        self.current_user = current_user

        self.session = str(uuid.uuid4())
        self.temp_dir = temp_file_service.create_temp_dir(self.session)

        self.presentation_dir = get_presentation_dir(self.data.presentation_id)

    def __del__(self):
        temp_file_service.cleanup_temp_dir(self.temp_dir)

    async def post(self, logging_service: LoggingService, log_metadata: LogMetadata):
        logging_service.logger.info(
            logging_service.message(self.data.model_dump(mode="json")),
            extra=log_metadata.model_dump(),
        )

        await self.fetch_presentation_assets()

        with get_sql_session() as sql_session:
            presentation = sql_session.get(
                PresentationSqlModel, self.data.presentation_id
            )

        # Handle cases where title might be empty, None, or the old default prompt text
        title = presentation.title
        if (not title or 
            title == "Title of this presentation in about 3 to 8 words" or
            title == "Presentation" or
            len(title.strip()) == 0):
            # Generate a more descriptive fallback based on the presentation prompt
            if presentation.prompt and len(presentation.prompt.strip()) > 0:
                # Take first few words from prompt as title
                words = presentation.prompt.strip().split()[:4]
                title = " ".join(words).title()
            else:
                title = f"Presentation {presentation.id[:8]}"

        ppt_path = os.path.join(
            self.presentation_dir,
            sanitize_filename(f"{title}.pptx")
        )
        ppt_creator = PptxPresentationCreator(self.data.pptx_model, self.temp_dir)
        ppt_creator.create_ppt()
        ppt_creator.save(ppt_path)

        # Return just the filename instead of the full path for URL construction
        filename = sanitize_filename(f"{title}.pptx")
        
        response = PresentationAndPath(
            presentation_id=self.data.presentation_id, path=filename
        )

        with get_sql_session() as sql_session:
            presentation = sql_session.get(
                PresentationSqlModel, self.data.presentation_id
            )
            # Store the full path in database for internal use, but return only filename
            presentation.file = ppt_path
            sql_session.commit()

        # Save presentation to user's account if user is authenticated
        if self.current_user:
            try:
                # Read the generated PPT file
                with open(ppt_path, 'rb') as f:
                    ppt_content = f.read()
                
                # Save to user's presentations directory using file_manager
                with get_session() as auth_session:
                    user_presentation = file_manager.save_presentation(
                        user_id=self.current_user.id,
                        title=title,
                        file_content=ppt_content,
                        file_extension=".pptx",
                        session=auth_session
                    )
                    
                logging_service.logger.info(
                    f"Saved presentation to user account: {user_presentation.id}",
                    extra=log_metadata.model_dump(),
                )
            except Exception as e:
                logging_service.logger.error(
                    f"Failed to save presentation to user account: {str(e)}",
                    extra=log_metadata.model_dump(),
                )

        logging_service.logger.info(
            logging_service.message(response.model_dump(mode="json")),
            extra=log_metadata.model_dump(),
        )

        return response