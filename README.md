# Lee's Umbrel App Store

This is a personal [umbrelOS community app store](https://github.com/getumbrel/umbrel-community-app-store). 

To add it: umbrelOS → App Store → ⋯ → Community App Stores → paste
`https://github.com/lee-antics/lee-umbrel-apps`.

## Apps

- **Tofa** (`lee-tofa`): self-hosted media server. Your `Home/Videos` folder is
  mounted read-only at `/media`; add that as a library in Tofa. To use a
  network drive, add it in Files → Network, pick a folder on it for the
  **Network Media** slot in Tofa's app settings, then add `/network-media` as a
  library in Tofa.
- **Beszel** (`lee-beszel`): monitoring hub, plus an agent for the
  Umbrel itself (system, Docker containers and the Intel GPU). To monitor the
  Umbrel, click **Add System** in Beszel and enter `/beszel_socket/beszel.sock`
  as the host. To move an existing hub here, restore its backup (or copy its
  `beszel_data` folder into the app's `data/hub` folder) and restart the app;
  agents that trusted the old hub keep working because its key comes with it.
- **Recyclarr** (`lee-recyclarr`): syncs TRaSH Guides custom formats, quality
  profiles and sizes to Radarr and Sonarr once a day at 4am. The app page
  shows the latest sync log. There is no settings screen: put your
  `recyclarr.yml` and `secrets.yml` in the app's `data/config` folder. On the
  same Umbrel, Radarr and Sonarr are at `http://radarr_server_1:7878` and
  `http://sonarr_server_1:8989`. Keep these files out of this repo; they hold
  API keys.

## Updates

`.github/workflows/update-apps.yml` runs daily. When an app's upstream
publishes a newer `X.Y.Z` image, it pins the compose file to that tag and
digest and raises the app version, so umbrelOS shows an **Update** button. Run
it by hand from the repo's Actions tab ("Update apps" → Run workflow). Apps
and their images are listed in `.github/scripts/update_apps.py`.

To hold apps on their current versions, disable the workflow in the Actions tab.
