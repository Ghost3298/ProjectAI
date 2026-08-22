import { Component } from '@angular/core';
import { Chat } from "../../features/chat/chat";
import { Side } from "../side/side";

@Component({
  selector: 'app-main',
  imports: [Chat, Side],
  templateUrl: './main.html',
  styleUrl: './main.css',
})
export class Main {}
