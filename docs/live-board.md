# Live board on Cloudflare Pages, private to the team

The board (`tools/coord.py board`) is published to Cloudflare Pages by the
GitHub Action in `.github/workflows/board.yml` every time something under
`coord/` is pushed to `main`. Cloudflare Access puts a login in front of it so
only the email addresses we list can open it. Both are on free plans.

The same deploy carries a second tab, **Environment** (`environment.html`; the old `environments.html` redirects): pictures
and replays of each environment for people, built from `visuals/` (see
`visuals/README.md`). It is published whenever `visuals/` changes on `main`.

How live is it: the board changes only when an agent pushes. A push shows up on
the page roughly a minute later (Action run + upload), and the page reloads
itself every 60 seconds.

Why a GitHub Action and not Cloudflare's own Git integration: Cloudflare's free
plan builds at most 500 times a month, one at a time, and our agents push far
more often than that over a weekend. The Action builds the page itself and only
uploads the result, and it collapses bursts of pushes into one deploy.

## One-time setup (about 10 minutes, one person)

Needs: the repo on GitHub, and a free Cloudflare account.

1. **Account ID.** In the Cloudflare dashboard open **Workers & Pages**; the
   Account ID is shown on that page. Copy it.
2. **API token.** Create an API token (*My Profile* > *API Tokens* >
   *Create Token* > *Create Custom Token*). Under **Permissions** pick the
   three dropdowns *Account* | *Cloudflare Pages* | *Edit* (the first dropdown
   must say *Account*, not *User* or *Zone*). Under **Account Resources** pick
   *Include* and your account. Copy the token (shown once).
3. **Give both to GitHub** (run in the repo; each command prompts for the value):

   ```bash
   gh secret set CLOUDFLARE_ACCOUNT_ID
   gh secret set CLOUDFLARE_API_TOKEN
   gh variable set CF_PAGES_PROJECT --body "<a-project-name>"   # optional, default: junction-board
   ```

   The project name becomes the address `<project-name>.pages.dev` (Cloudflare
   adds a suffix if the name is taken).
4. **First deploy.** `gh workflow run board` (or push any change under
   `coord/`). The first run creates the Pages project and uploads the board.
   Check it with `gh run watch`; the run log prints the URL.

   **The page is public at this point.** Do step 5 straight away.
5. **Lock it with Access** (Cloudflare's documented procedure for a
   `*.pages.dev` domain):
   0. **Zero Trust organization first.** Access needs one. In the dashboard open
      **Zero Trust**, choose a team name, and pick the **Free** plan. Cloudflare
      asks for payment details even on Free but does not charge. Until this
      exists the option in the next step may be missing.
   1. **Workers & Pages** > the project > **Settings** > **General** >
      **Enable access policy**. This creates a policy that covers preview
      deployments only.
   2. Select **Manage** on that policy, open the application under
      **Access** > **Applications**, and choose **Configure**.
   3. Under **Public hostname**, delete the wildcard `*` in the **Subdomain**
      field and save (rename the application if it complains). The production
      address `<project-name>.pages.dev` is now behind Access.
   4. In that application's policy, allow exactly the teammates' email
      addresses (rule type *Emails*). They log in with a one-time code sent to
      that address.
   5. Optional: go back to the project > **Settings** and select **Enable
      access policy** again to also cover preview deployments. We only deploy
      to production, so this does not matter much.

6. **Verify.** Open the URL in a private browser window: you must get the
   Access login, not the board. Then put the URL into `coord/project.md` so
   every agent and teammate can find it.

## If the workflow fails

The step **Check Cloudflare credentials** runs before the deploy and its error
says what to fix (bad Account ID, token rejected, token missing the Pages
permission, or Account ID not the token's account). Read it with
`gh run view --log-failed`. After editing a token's permissions in Cloudflare
the token value stays the same, so the GitHub secret does not need updating;
just run `gh workflow run board` again. A newly created token does need
`gh secret set CLOUDFLARE_API_TOKEN`.

## Operating notes

- Redeploy by hand: `gh workflow run board`.
- Deploys run only for pushes that touch `coord/`, `tools/coord.py` or the
  workflow. Code-only pushes do not redeploy, so the "recent commits" panel can
  lag until the next coordination change.
- Until the two secrets exist the workflow still runs, builds the board and
  stops with a notice. It does not fail.
- On a private repo each run uses about a minute of the 2,000 free GitHub
  Actions minutes per month. Public repos are not metered.
- The local alternative needs no setup: `python3 tools/coord.py board --serve`.

## Not verified

Written from Cloudflare's docs on 2026-11-14, without an account to test against:

- The workflow has not run yet (the repo had no remote when it was written).
- Cloudflare's docs do not say whether uploads made this way count toward the
  500 builds a month. If deploys start failing with a quota error, check the
  project's deployments page.
- That Access is free for up to 50 users is from memory; Cloudflare's setup
  docs only confirm the Free plan exists and that it asks for payment details
  without charging.
