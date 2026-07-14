# n8n workflow: IntelliDigest → Telegram

**Bundled n8n in Docker:** the default [`docker-compose.yml`](../docker-compose.yml) does **not** include n8n. To run IntelliDigest **with** n8n in one stack, use:

`docker compose -f docker-compose.with-n8n.yml up -d --build`

You can also host n8n elsewhere and paste its webhook URL into IntelliDigest **Tools** (same as always).

## Import

1. Open your n8n instance (e.g. `http://localhost:5678` when using `docker-compose.with-n8n.yml`).
2. **Workflows** → menu **⋯** → **Import from File**.
3. Select [`intellidigest-telegram.json`](../n8n/intellidigest-telegram.json).
4. Open the imported workflow.

## Telegram bot credential

1. Talk to [@BotFather](https://t.me/BotFather) on Telegram, create a bot, and copy the **HTTP API token**.
2. In n8n, go to **Credentials** → **New** → **Telegram API** (or edit the **Send Telegram** node and **Create New Credential**).
3. Paste the bot token and save.
4. Assign that credential to the **Send Telegram** node.

## Activate and copy the webhook URL

1. Click **Inactive** → **Active** so the workflow is enabled.
2. Open the **Webhook** node. Copy the **Production URL** (or Test URL while debugging).  
   It looks like:  
   `https://<your-n8n-host>/webhook/intellidigest-telegram`  
   For local Docker, n8n often shows `http://localhost:5678/webhook/intellidigest-telegram` (only reachable from the same machine unless you expose the port).

## IntelliDigest UI Setup Wizard

1. Run IntelliDigest (Docker or [DOCKERLESS.md](DOCKERLESS.md)).
2. Open the **Tools** tab in the sidebar.
3. Click the prominent **Connect Telegram** button.
4. Follow the intuitive 11-step interactive wizard! It will guide you through acquiring your Chat ID, entering the webhook URL, and will automatically send a test ping to verify the connection.

### Formatting
IntelliDigest natively strips unsupported Markdown elements and converts responses to Telegram's HTML format. The `intellidigest-telegram.json` workflow is already configured to parse this HTML properly out of the box!

## Payload (reference)

The FastAPI app posts JSON like:

```json
{
  "action": "verify_telegram",
  "telegram_chat_id": "123456789",
  "assistant_message": "...",
  "user_message": "",
  "persona": "",
  "channel": "research_chat",
  "title": "IntelliDigest"
}
```

or `action: "save_message"` with filled `assistant_message` / `user_message`.

The **Prepare Telegram message** code node normalizes `body` vs root fields so minor n8n version differences still work.

## Path

The webhook path is **`intellidigest-telegram`**. To change it, edit the **Webhook** node path and use the new URL in IntelliDigest.
