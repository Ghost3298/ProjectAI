import { HttpClient } from "@angular/common/http";
import { Injectable } from "@angular/core";
import { Observable } from "rxjs";

export interface JobTurn {
    start_time: number;
    end_time: number;
    speaker_label: string;
    text: string | null;
    speaker_id: string | null;
}

export interface JobEntity {
    type: string;
    value: string;
}

export interface JobDetail {
    job_id: string;
    status: string;
    transcript: string | null;
    detected_language: string | null;
    summary: string | null;
    entities: JobEntity[] | null;
    error_message: string | null;
    created_at: string | null;
    turns: JobTurn[];
}

@Injectable({providedIn: 'root'})

export class JobService {

    constructor(private http: HttpClient){}

    uploadJob(file: File, sessionId: string):  Observable<{ job_id: string }>{
        const formData = new FormData()
        formData.append('file', file)
        formData.append('session_id', sessionId)
        return this.http.post<{ job_id: string }>('http://localhost:8080/jobs', formData)
    }

    getJob(id: string): Observable<JobDetail>{
        return this.http.get<JobDetail>(`http://localhost:8080/jobs/${id}`)
    }
}
