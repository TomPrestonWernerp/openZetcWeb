# openzetc-cli

openZetc command line client.

First-stage scope:

- remote management through `~/.openzetc/config.toml`
- browser login
- API Key import through `--api-key`
- `whoami`, `status`, and `logout`
- server discovery and compatibility check for openZetc `>=0.7.1`
- `openzetc kb upload` for knowledge base file uploads
- `openzetc agent eval` for running existing Langfuse dataset experiments with a logged-in remote
