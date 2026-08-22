import { HttpClient } from "@angular/common/http";
import { Injectable } from "@angular/core";
import { Observable } from "rxjs";

@Injectable({providedIn: 'root'})

export class JobService {

    constructor(private http: HttpClient){}

    uploadJob(file: File):  Observable<{ job_id: string }>{
        const formData = new FormData()
        formData.append('file', file)
        return this.http.post<{ job_id: string }>('http://localhost:8000/jobs', formData)
    }

    getJob(id: string): Observable<{job_id: string, status: string, transcript: string | null}>{
        return this.http.get<{ job_id: string; status: string; transcript: string | null }>(
            `http://localhost:8000/jobs/${id}`
        )
    }
}