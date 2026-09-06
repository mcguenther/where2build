#!/usr/bin/env bash
# Fetch the two inputs a local MOTIS needs into motis/data-input/.
#
# Run this on the host, not in a container: it is the only step that touches
# the internet, and keeping it out of the image means the compose services need
# no network of their own.
#
#   ./motis/fetch-data.sh
#   docker compose -f docker-compose.yml -f docker-compose.local-routing.yml up
#
# Both files are licensed CC-BY 4.0 and must be attributed:
#   - OpenStreetMap contributors (https://www.openstreetmap.org/copyright)
#   - DELFI e. V. (https://www.opendata-oepnv.de/)
set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
out="$here/data-input"
mkdir -p "$out"

# The street network. Saxony only -- the app never routes beyond the state, and
# the extract decides how long the import takes and how much RAM it wants.
# Any .osm.pbf works; a city extract is enough to try the setup out, a Germany
# extract is what you want if destinations may lie outside Saxony.
osm_url="${W2B_OSM_URL:-https://download.geofabrik.de/europe/germany/sachsen-latest.osm.pbf}"

# The timetable. This is the file Transitous itself feeds to MOTIS for Germany
# -- the raw DELFI "Deutschlandweite Sollfahrplandaten (GTFS)", republished so
# it can be fetched without the registration opendata-oepnv.de asks for.
# Updated weekly, on Mondays.
gtfs_url="${W2B_GTFS_URL:-https://api.transitous.org/gtfs/de_DELFI.gtfs.zip}"

ua="${APP_CONTACT:-where2build (https://github.com/)}"

fetch() {
  local url="$1" target="$2"
  echo "→ $url"
  # Into a .part file and only then into place: these are re-run to pick up a
  # new timetable, and resuming onto a file whose remote side has changed
  # would splice two vintages together without any error.
  curl --fail --location --progress-bar \
       --user-agent "$ua" --output "$target.part" "$url"
  mv "$target.part" "$target"
  ls -lh "$target"
}

fetch "$osm_url"  "$out/osm.pbf"
fetch "$gtfs_url" "$out/timetable.gtfs.zip"

echo
echo "Inputs ready in $out. Next:"
echo "  docker compose -f docker-compose.yml -f docker-compose.local-routing.yml up --build"
