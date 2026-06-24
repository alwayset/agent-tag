# Lark setup

How to create a Lark bot and wire it into Agent Tag. Steps are for **Lark
international** (`open.larksuite.com`). Feishu (mainland China) is the same flow
on a different domain — see [Lark vs Feishu](#lark-vs-feishu) at the end.

You'll come away with three values to paste into the admin console's
**Connections** page:

- **App ID** (`cli_...`)
- **App Secret**
- **Domain** — `https://open.larksuite.com` (Lark) or `https://open.feishu.cn` (Feishu)

---

## 1. Create a custom app

1. Go to the **Lark Developer Console**: <https://open.larksuite.com/app>.
2. Click **Create Custom App** (custom = built for your own tenant).
3. Give it a name (e.g. "Agent Tag") and an icon, then **Create**.
4. On the app's **Credentials & Basic Info** page, copy the **App ID** and
   **App Secret**. These go into the Agent Tag **Connections** page.

## 2. Enable the bot

1. In the left sidebar open **Add Features** → **Bot**.
2. Click **Enable** (a.k.a. **Add Bot**).

Without the Bot feature the app can't receive or send chat messages.

## 3. Add permission scopes

In the left sidebar open **Permissions & Scopes** and add the following scopes.
Names are matched exactly as the console lists them; the readonly/granular
variants are what Lark exposes today.

| Scope | What it's for |
|-------|---------------|
| `im:message` | Read message content the bot receives. |
| `im:message.group_at_msg:readonly` | Receive **group messages that `@`-mention the bot** — the core trigger. |
| `im:message:send_as_bot` | Send messages as the bot (replies). |
| `im:resource` | Download attachments/images users send (`message_resource.get`). |

> If you also want the bot to read **every** group message (not only
> `@`-mentions), add `im:message.group_msg`. Agent Tag defaults to
> mention-only (`require_mention=True` on the channel policy), so the
> `group_at_msg` scope is sufficient for the standard setup.

After adding scopes you must **publish a new version** (step 5) for them to
take effect.

## 4. Subscribe to the message event over a long connection (WebSocket)

Agent Tag's Lark adapter receives messages over a **WebSocket long connection**
(`lark_oapi.ws.Client`) — no public callback URL or tunnel needed.

1. In the left sidebar open **Events & Callbacks** → **Event Configuration**
   (older consoles: **Event Subscriptions**).
2. For the subscription method, choose **Use long connection** (WebSocket).
   - This mode supports **event** subscriptions only (not callback
     subscriptions) — which is exactly what we need.
3. Click **Add Events** and add:
   - **Receive message** — event key **`im.message.receive_v1`**.
4. Adding the event will prompt for any scopes it needs; confirm they match
   step 3 (it requires `im:message` / the group-at-msg readonly scope).

> **Lark international caveat.** Some Lark *international* tenants do **not**
> expose the **Use long connection** option in the console (it's a platform
> restriction; Feishu always has it). If you don't see the long-connection
> option, the long-connection adapter can't connect for that tenant — you'd
> need to fall back to **callback (webhook) mode** with a public HTTPS URL,
> which the current adapter does not implement. Confirm long connection is
> available for your tenant before relying on it. If it's missing, open an
> issue so we can prioritise the webhook fallback.

## 5. Publish / enable the app

1. In the left sidebar open **Version Management & Release**.
2. **Create a version** — set a version number and availability scope
   (who in the tenant can use the app).
3. **Publish**. For custom apps in a self-managed tenant the version may
   require **admin approval** in the Lark Admin Console before it goes live.

Scopes and events only take effect **after** a published version is live, so
re-publish whenever you change them.

## 6. Add the bot to a group

1. Open the **Lark client** and go to (or create) the group you want the
   teammate to live in.
2. Group **Settings** → **Bots** (a.k.a. **Group Bots**) → **Add Bot**.
3. Find your app by name and add it.

## 7. Wire it into Agent Tag

1. Start Agent Tag and open the admin console (<http://localhost:8765>).
2. **Connections**: paste **App ID**, **App Secret**, and the **Domain**
   (`https://open.larksuite.com`), and pick a backend.
3. **Restart** the process so the Lark adapter binds with the new creds
   (`docker compose restart`, or re-run `agent-tag serve`).
4. **Workspace**: bind the group. Then `@`-mention the bot in the group —
   the user auto-enrolls and the teammate replies.

---

## Lark vs Feishu

Same app model, two clouds:

| | International (Lark) | Mainland China (Feishu / 飞书) |
|--|----------------------|-------------------------------|
| Developer console | `open.larksuite.com` | `open.feishu.cn` |
| **Domain** to set in Connections | `https://open.larksuite.com` | `https://open.feishu.cn` |
| Long-connection events | May not be exposed on some tenants (see caveat above) | Supported |

An app created on one cloud does **not** work on the other — pick the cloud
your team's chat actually runs on and set `LARK_DOMAIN` / the Connections
Domain field to match.
