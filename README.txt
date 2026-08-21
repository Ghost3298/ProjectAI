Worth flagging clearly before we move on: this same setup — toolkit install, 
nvidia-ctk configure, Docker restart, deploy: block — will need repeating on your PC with the 5060 
the first time you run this project there. Nothing about it is committed into your code or docker-compose.yml 
in a way that magically works elsewhere; the toolkit install specifically is host-level, per-machine. 
Worth adding a line to your project's README (or the checklist doc) so future-you doesn't have to rediscover 
this from scratch on the other machine.