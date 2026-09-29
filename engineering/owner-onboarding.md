# Owner onboarding (private Kiln)

Kiln on https://kiln.plainlist.space is a **personal private AI**. Public self-registration is disabled.

## First owner (empty database only)

On the Mac that runs the API:

```bash
cd /Users/rainhuang/Desktop/models/kiln/backend
../.venv/bin/python -m app.cli create-owner --username YOURNAME
```

Password is prompted (or `KILN_BOOTSTRAP_PASSWORD`). Never commit it.

## Additional users (owner-issued)

```bash
cd /Users/rainhuang/Desktop/models/kiln/backend
../.venv/bin/python -m app.cli create-user --username NEWUSER
```

Password via prompt or `KILN_NEW_USER_PASSWORD`.

## Login

Open https://kiln.plainlist.space and sign in with the issued username/password.

## Forgot owner password (local only)

```bash
cd /Users/rainhuang/Desktop/models/kiln/backend
../.venv/bin/python -m app.cli reset-password --username rain
```

Do not run recovery over the public internet.
