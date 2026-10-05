- [x] check if langsmith deploy possible before commiting
  - [x] pricing: deploy start from Plus plan, $39/mo
  - [x] geo availability: uncertain
- [x] check deploy is Russia
  - [x] PaaS: Amvera Cloud
  - [ ] ~~VPS: Timeweb~~
    - [ ] ~~Docker + Docker Compose setup~~
  - [x] choose model provider: https://neuraldeep.ru
  - [x] choose model https://neuraldeep.ru/models/qwen3-8-27b
- [ ] prompt
  - [ ] specify query format
  - [ ] response needs reference
- [x] model and tool streaming
- [ ] define search_arcanum return type, it is used by llm under the hood
- [x] use ainvoke or astream, because server call
- [x] short-term memory
- [ ] structured output: answer + reference
- [x] make it possible to use chat more then for 1 message
- [ ] format ##, ###, **: .md formatter?
- [ ] hide toolcall result properly, without "results" check

---

- [ ] mcp math tools
- [ ] amvera.yaml -> Dockerfile

---

- [ ] handle reconnect on front-end, store thread_id in local storage(from event type 'thread_created') and pass to new ws: `wss://<домен>.amvera.io/ws?thread_id=${threadId}`