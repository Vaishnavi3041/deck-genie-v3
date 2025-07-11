export interface GenerateRequestBody {
    prompt?: string;
    document?: string;
    tone: string;
}

export interface SlideData {
    id: string;
    thumbnail: string;
}

export interface PresentationResponse {
    presentation: {
        id: string;
        created_at: string;
        prompt: string;
        n_slides: number;
        file: string;
    };
    slides: SlideData[];
} 