import { HttpClient } from "@angular/common/http";
import { Injectable } from "@angular/core";
import { Observable } from "rxjs";

export interface SpeakerSummary {
    speaker_id: string;
    name: string;
    status: string;
    created_at: string | null;
}

@Injectable({providedIn: 'root'})
export class SpeakersService {

    constructor(private http: HttpClient){}

    enrollSpeaker(name: string, file: File): Observable<{ speaker_id: string }>{
        const formData = new FormData()
        formData.append('name', name)
        formData.append('file', file)
        return this.http.post<{ speaker_id: string }>('http://localhost:8080/speakers', formData)
    }

    listSpeakers(): Observable<SpeakerSummary[]>{
        return this.http.get<SpeakerSummary[]>('http://localhost:8080/speakers')
    }

    deleteSpeaker(id: string): Observable<{ speaker_id: string }>{
        return this.http.delete<{ speaker_id: string }>(`http://localhost:8080/speakers/${id}`)
    }
}
