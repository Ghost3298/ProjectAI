import { HttpClient } from "@angular/common/http";
import { Injectable } from "@angular/core";
import { Observable } from "rxjs";
import { JobTurn } from "./jobs.service";

export interface SessionSummary {
    session_id: string;
    name: string | null;
    created_at: string | null;
    recording_count: number;
    status: string;
    detected_language: string | null;
    first_recording_name: string | null;
}

export interface SessionJob {
    job_id: string;
    original_filename: string;
    status: string;
    transcript: string | null;
    detected_language: string | null;
    error_message: string | null;
    created_at: string | null;
    turns: JobTurn[];
}

export interface SessionNoteEntry {
    note_id: string;
    text: string;
    created_at: string | null;
}

export interface SessionDetail {
    session_id: string;
    name: string | null;
    created_at: string | null;
    jobs: SessionJob[];
    notes: SessionNoteEntry[];
}

@Injectable({providedIn: 'root'})
export class SessionsService {

    constructor(private http: HttpClient){}

    createSession(): Observable<{ session_id: string }>{
        return this.http.post<{ session_id: string }>('http://localhost:8080/sessions', {})
    }

    listSessions(): Observable<SessionSummary[]>{
        return this.http.get<SessionSummary[]>('http://localhost:8080/sessions')
    }

    getSession(id: string): Observable<SessionDetail>{
        return this.http.get<SessionDetail>(`http://localhost:8080/sessions/${id}`)
    }

    renameSession(id: string, name: string): Observable<{ session_id: string, name: string | null }>{
        return this.http.patch<{ session_id: string, name: string | null }>(`http://localhost:8080/sessions/${id}`, { name })
    }

    addNote(sessionId: string, text: string): Observable<SessionNoteEntry>{
        return this.http.post<SessionNoteEntry>(`http://localhost:8080/sessions/${sessionId}/notes`, { text })
    }
}
