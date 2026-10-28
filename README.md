# Lee's Umbrel App Store

A personal [umbrelOS community app store](https://github.com/getumbrel/umbrel-community-app-store).

To add it: umbrelOS → App Store → ⋯ → Community App Stores → paste
`https://github.com/lee-antics/lee-umbrel-apps`.

## Apps

- **Tofa** (`lee-tofa`): self-hosted media server. Your `Home/Videos` folder is
  mounted read-only at `/media`; add that as a library in Tofa.

## Updates

`.github/workflows/update-tofa.yml` runs daily. When Tofa publishes a newer
`X.Y.Z` image, it pins the compose file to that tag and digest and raises the
app version, so umbrelOS shows an **Update** button for Tofa. Run it by hand
from the repo's Actions tab ("Update Tofa" → Run workflow).

To hold Tofa on its current version, disable the workflow in the Actions tab.
