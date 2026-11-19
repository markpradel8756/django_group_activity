# Relay · SMS Workspace

Relay is a Django web application for the IT 120 group assignment. It uses textbee.dev to send SMS through a registered Android phone. The project demonstrates Django forms, the ORM, third-party API calls, error handling, and automated testing.

## Features

- Dashboard with database-backed counts, seven days of activity, and recent attempts.
- International phone validation, saved recipient selection, a live preview, and SMS segment estimates.
- One outbound SMS per submission, with duplicate protection and feedback from textbee.
- Searchable message history with status and date filters, pagination, and full message details.
- Delivery updates through signed textbee webhooks and an on-demand refresh in message details.
- Searchable contacts with add, edit, and delete operations.
- Device and API connection checks that keep credentials on the server.

The stack is Python 3.12, Django 5.2 LTS, SQLite, the textbee.dev REST API via Requests, HTML, responsive CSS, JavaScript, and Lucide icons. Dependencies are pinned. The icons and their license are included locally.

## Project structure

```text
.
├── manage.py                          Django command runner
├── relay/                             Project settings, root URLs, and WSGI entry point
├── messaging/
│   ├── models.py                      SMS attempts and contacts
│   ├── validators.py                  Phone and SMS length rules
│   ├── forms.py                       Form fields and input checks
│   ├── views.py and urls.py           Pages, submissions, and the callback route
│   ├── textbee_service.py             textbee requests, status updates, and safe errors
│   ├── middleware.py                  User-friendly handling of unexpected view errors
│   ├── migrations/                    Versioned database schema
│   ├── templates/                     Django page templates and error page
│   ├── static/messaging/              CSS, JavaScript, and SVG icons
│   └── tests.py                       Tests with mocked provider calls
├── docs/DEMO.md                       Video script and submission checklist
├── requirements.txt                  Python dependencies
├── .env.example                      Example local configuration
└── .gitignore                         Local files excluded from Git
```

## Local installation

Install Python 3.12, Git, and a browser. VS Code is optional. Open a terminal in the folder containing `manage.py`.

### Windows PowerShell

```powershell
python -m venv .venv
$relayPython = '.\.venv\Scripts\python.exe'
if (!(Test-Path $relayPython)) { $relayPython = '.\.venv\bin\python.exe' }
& $relayPython -m pip install -r requirements.txt
if (!(Test-Path .env)) { Copy-Item .env.example .env }
& $relayPython manage.py migrate
& $relayPython manage.py check
& $relayPython manage.py runserver 127.0.0.1:8000
```

Most Windows installs use `Scripts`. MSYS2 Python uses `bin`. Using the virtual environment's Python directly also works when PowerShell blocks activation scripts. If Windows opens the Microsoft Store instead of Python, use the Python launcher `py -3.12 -m venv .venv` or the path to your installed Python.

### macOS or Linux

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.txt
test -e .env || cp .env.example .env
python manage.py migrate
python manage.py check
python manage.py runserver 127.0.0.1:8000
```

Open [Relay on localhost](http://127.0.0.1:8000/). Stop the development server with Ctrl+C. The dashboard, editor, history, and contacts run before you configure textbee.

## Configure textbee.dev

1. Create a textbee account and verify its email. Install the textbee app on an Android phone with an SMS-capable SIM and an internet connection. [textbee setup guide](https://textbee.dev/docs/getting-started/setting-up-textbee)
2. Pair the phone from the dashboard, grant it permission to send SMS, and keep the gateway enabled and the phone online. Copy the Device ID from **Devices**. [Device registration](https://textbee.dev/docs/getting-started/registering-a-device)
3. Generate an API key for Relay in **API Keys**. In your local `.env`, set `TEXTBEE_API_KEY` and `TEXTBEE_DEVICE_ID`. Relay sends through that device and uses the phone's default SMS SIM. [API keys and authentication](https://textbee.dev/docs/getting-started/api-keys)
4. If `DJANGO_SECRET_KEY` is still a placeholder, generate a key in a private terminal and paste it into `.env`. Keep that terminal out of recordings and screenshots.

   ```powershell
   & $relayPython -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
   ```

   With an activated environment on macOS or Linux, use `python` in place of `& $relayPython`.

5. Restart Django and choose **Settings → Check connection**. This checks whether textbee recognizes your key and whether the configured device is enabled. Test the phone's actual ability to send with one SMS to a consenting recipient.

If you are upgrading an existing Relay workspace, run `manage.py migrate` before restarting Django. Historical Twilio attempts keep their provider name, reference, and last recorded status in history. New attempts use textbee.

| Variable | Purpose |
| --- | --- |
| `DJANGO_SECRET_KEY` | Signs session-related data. A unique value is required with debug off. |
| `DJANGO_DEBUG` | Defaults to `True` for the local classroom demo. `DEBUG` is accepted as a fallback. |
| `DJANGO_ALLOWED_HOSTS` | Comma-separated hostnames. Defaults to localhost addresses. |
| `DJANGO_TIME_ZONE` | Time zone used for timestamps, chart days, and history date filters. Defaults to `Asia/Manila`. |
| `DJANGO_REQUIRE_LOGIN` | Set to `True` to enable Django sign-in in development. Sign-in is required with debug off. |
| `DJANGO_SECURE_COOKIES` | Enable for HTTPS-only browser access. Defaults to on with debug off when the variable is unset. |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | Comma-separated HTTPS origins to trust for browser form submissions when using a reverse proxy. |
| `TEXTBEE_API_KEY` | API key used only by Django. |
| `TEXTBEE_DEVICE_ID` | ID of the registered Android device that sends Relay messages. |
| `TEXTBEE_WEBHOOK_SECRET` | Optional signing secret shared by Django and the textbee webhook subscription. |

## Send and track an SMS

1. Open **Send SMS**. Enter an authorized number with its country code and leading `+`, or choose an existing contact.
2. Enter the text. Review the recipient and message in **Message preview**. On a phone, **Review preview** takes you to that section.
3. Select **Send SMS** once. Relay saves the attempt before contacting textbee and opens its details page.
4. Review the provider feedback. Once a textbee batch ID appears, select **Refresh status** to look up the latest delivery state. Use **Message History** to find it later.

| Status | Meaning in Relay |
| --- | --- |
| Submitted | textbee accepted the request. The SMS may be queued, sent to the phone, or accepted by the carrier. |
| Delivered | textbee received a delivery report from the carrier. |
| Failed | A definite local configuration problem, provider rejection, or provider send failure. |
| Undelivered | A historical provider reported unsuccessful delivery after submission. |
| Pending | The attempt exists and the application has yet to record a provider outcome. |
| Unknown | textbee has no confirmed state or the request outcome is uncertain. Check the textbee dashboard before sending again. |

The dashboard counts the current statuses. The Failed card includes both Failed and Undelivered, while the Submitted card counts messages awaiting delivery confirmation. The chart includes all attempts by creation date.

### Optional delivery callbacks

`localhost` cannot receive requests from textbee. To test callbacks, route `/webhooks/textbee/status/` through a publicly reachable HTTPS tunnel or reverse proxy. Keep the workspace on localhost or use the shared-workspace configuration below. [textbee webhooks](https://textbee.dev/docs/webhooks)

1. Generate a random signing secret of at least 20 characters. Set `TEXTBEE_WEBHOOK_SECRET` in `.env` and add your public hostname to `DJANGO_ALLOWED_HOSTS`. Restart Django.
2. In the textbee dashboard, create a webhook subscription using `https://your-host.example/webhooks/textbee/status/` and the same signing secret. Select **MESSAGE_SENT**, **MESSAGE_DELIVERED**, and **MESSAGE_FAILED**.
3. Send an authorized SMS and reload its details page after textbee reports a new status. Relay validates the timestamped signature and matches the batch ID, device ID, and recipient. Repeated or late progress events cannot overwrite a final status. [Webhook event reference](https://textbee.dev/docs/webhooks/events)

With callbacks off, use **Refresh status** on a record with a saved textbee batch ID. Some carriers never return a delivery report. [Delivery states](https://textbee.dev/docs/sending-sms/delivery-status)

## Testing

### Automated tests

Run these from the project root in PowerShell with the `$relayPython` variable above.

```powershell
& $relayPython manage.py check
& $relayPython manage.py makemigrations --check --dry-run
& $relayPython manage.py test
```

On macOS or Linux, replace `& $relayPython` with `python` in the activated environment. Django creates an isolated test database. The tests cover form validation, contact CRUD, history and filtering, the send and refresh workflows, duplicate submissions, provider errors, and signed callbacks. Provider requests are mocked and use no SMS credits.

### Browser walkthrough

1. Open the Dashboard, Send SMS, Message History, Contacts, and Settings. Repeat in a narrow browser window or device emulation.
2. Type an international number and a short draft on **Send SMS**. Verify that the number, text, character count, and segment estimate change as you type. Add an emoji to check the Unicode estimate.
3. Submit a malformed number or whitespace-only message. Check that an error is displayed and that no attempt is added.
4. Add a contact in **Contacts**, search for it, edit it, open Send SMS from its row, and confirm that its number appears in the editor. Delete the contact when finished.
5. With the textbee configuration blank, use **Check connection** to verify that the app reports the missing setup.

### Live textbee integration test

1. Complete textbee setup, keep the registered phone online, and get consent from a recipient who can verify receipt.
2. Send one short SMS. Use the actual recipient number only in the private workspace. Verify the textbee batch ID and reported status in **Message Details**.
3. Refresh the status, or wait for the callback and reload the page. If the request fails, compare the safe error code privately with the textbee dashboard.
4. Check that the attempt appears in history and the dashboard counts reflect its current status. Review the recipient handset with their permission.

## Security and known limitations

- Relay stores recipient numbers and SMS bodies in SQLite. Keep `.env`, the SQLite database, and screenshots with identifying data out of GitHub. Use sample text and obscure phone numbers and provider IDs in the video.
- The loopback demo opens without sign-in. Before exposing the full workspace, set `DJANGO_DEBUG=False`, provide a unique secret key, enable secure cookies, configure trusted hosts and HTTPS, and serve static files through the hosting server after running `python manage.py collectstatic`. Use a production WSGI server instead of Django's development server for a shared deployment.
- To enable local sign-in, set `DJANGO_REQUIRE_LOGIN=True`, run `python manage.py createsuperuser` with the virtual environment's Python, and restart the server. Signed-in users share the same contacts and history.
- Relay uses CSRF tokens for browser writes, server-side input validation, template escaping, and signature checks on textbee webhooks. A signed form token lets one browser submission create one attempt. Review the provider record before retrying an uncertain request.
- Segment counts are estimates. Relay enforces textbee's 9,000-byte limit using modified UTF-8, in which characters such as emoji can consume multiple bytes. Your phone, SIM and carrier affect sending and charges. [textbee sending guide](https://textbee.dev/docs/sending-sms/sending-sms)
- This project handles single-recipient outbound SMS. Incoming replies, campaigns, and multi-tenant accounts are outside the classroom project scope. Obtain consent, identify the sender, and respect opt-outs when testing.

## Group members and GitHub

Replace the open names with the actual group members and record their contributions after the work is done. These roles are suggestions.

| Group member | Suggested area | Actual contribution |
| --- | --- | --- |
| Add member name | Django models, views, routing, and database | Add completed work and PR links |
| Add member name | Templates, responsive UI, and JavaScript | Add completed work and PR links |
| Add member name | textbee, automated tests, and demo preparation | Add completed work and PR links |

One member creates the group's GitHub repository. From this folder, add the source and verify the staging list before committing. Replace `YOUR_GROUP_REPOSITORY_URL` with its actual clone URL.

```text
git init -b main
git add -- .
git status --short
git commit -m "Add Relay SMS workspace"
git remote add origin YOUR_GROUP_REPOSITORY_URL
git push -u origin main
```

Each member clones the repository with `git clone YOUR_GROUP_REPOSITORY_URL`. Start a branch from the latest `main` with `git switch main`, `git pull --ff-only`, and `git switch -c feature/contact-search`. Stage only your related files, use a specific commit message, and push with `git push -u origin feature/contact-search`. Open a pull request with a short description and your verification steps. Ask a teammate to review it before merging. Commit migration files with model changes and run `python manage.py migrate` after pulling schema changes.

Use the [video outline and submission checklist](docs/DEMO.md) to prepare for the instructor's review.
