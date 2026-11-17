- [x] FastAPI server
- [x] check if langsmith deploy possible before commiting
  - [x] pricing: deploy start from Plus plan, $39/mo
  - [x] geo availability: uncertain
- [x] check deploy is Russia
  - [x] PaaS: Amvera Cloud
  - [x] ~~VPS: Timeweb~~
    - [x] ~~Docker + Docker Compose setup~~
  - [x] choose model provider: https://neuraldeep.ru
  - [x] choose model https://neuraldeep.ru/models/qwen3-8-27b
- [ ] prompt
  - [ ] specify query format
  - [x] ~~response needs reference: not needed, stream writer instead~~
- [x] model and tool streaming
- [ ] define search_arcanum return type, it is used by llm under the hood
- [x] use ainvoke or astream, because server call
- [x] short-term memory
- [x] ~~structured output: answer + reference: not needed, stream writer instead~~
- [x] hide toolcall result properly, without "results" check
- [ ] remove old threads once a month
- [x] mcp math tools
- [x] amvera.yaml -> Dockerfile
- [x] (bug) apt "Network is unreachable"
- [x] (bug) amvera incident(https://status.yandex.cloud/ru/timeline?status=opened) with moscow_0 region, recreate app in warshaw region
- [x] (bug) neuraldeep changed free tier access, qwen3-8-27b-noreason is no nonger available; use qwen3.6-35b-a3b-noreason
- [x] (bug) 1-2 minutes before ConnectionError: handled connection timout

---

- [ ] measure latency/tokens of agent/total latency; add reranker; report diff

---

16/11/26 17:58:53
2026-11-16 13:58:53,459 INFO main: first token after 10.64s

16/11/26 18:00:57
2026-11-16 14:00:57,408 INFO main: first token after 9.26s

16/11/26 18:04:15
2026-11-16 14:04:15,706 INFO main: first token after 19.09s

16/11/26 18:07:35
2026-11-16 14:07:35,587 INFO main: first token after 14.47s

16/11/26 18:08:54
2026-11-16 14:08:54,852 INFO main: first token after 8.59s

2026-11-16 14:09:25,087 INFO main: first token after 10.50s

16/11/26 18:12:09
2026-11-16 14:12:09,961 INFO main: first token after 8.36s