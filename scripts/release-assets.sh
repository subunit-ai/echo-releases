#!/usr/bin/env bash

# Shared, read-only access to the one canonical draft reserved by build.yml.
# Call release_assets_load once, then release_asset_download for exact names.

release_assets_load() {
  if [ "$#" -ne 4 ]; then
    echo "error: release_assets_load REPO RELEASE_ID TAG PRERELEASE" >&2
    return 2
  fi
  RELEASE_ASSETS_REPO="$1"
  RELEASE_ASSETS_ID="$2"
  RELEASE_ASSETS_TAG="$3"
  RELEASE_ASSETS_PRERELEASE="$4"

  case "$RELEASE_ASSETS_ID" in
    ''|0|0*|*[!0-9]*) echo "error: invalid release id: $RELEASE_ASSETS_ID" >&2; return 1 ;;
  esac
  case "$RELEASE_ASSETS_PRERELEASE" in
    true|false) ;;
    *) echo "error: invalid prerelease flag: $RELEASE_ASSETS_PRERELEASE" >&2; return 1 ;;
  esac

  RELEASE_ASSETS_JSON=$(gh api "repos/$RELEASE_ASSETS_REPO/releases/$RELEASE_ASSETS_ID")
  jq -e --argjson id "$RELEASE_ASSETS_ID" \
    --arg tag "$RELEASE_ASSETS_TAG" \
    --argjson prerelease "$RELEASE_ASSETS_PRERELEASE" \
    '.id == $id and .tag_name == $tag and .draft == true and .prerelease == $prerelease' \
    <<<"$RELEASE_ASSETS_JSON" >/dev/null \
    || { echo "error: release $RELEASE_ASSETS_ID is not the canonical draft for $RELEASE_ASSETS_TAG" >&2; return 1; }

  local exact_count
  exact_count=$(gh api --paginate --slurp "repos/$RELEASE_ASSETS_REPO/releases?per_page=100" \
    | jq --arg tag "$RELEASE_ASSETS_TAG" '[.[][] | select(.tag_name == $tag)] | length')
  [ "$exact_count" -eq 1 ] \
    || { echo "error: $RELEASE_ASSETS_TAG has $exact_count releases; refusing ambiguous assets" >&2; return 1; }
}

release_asset_id() {
  if [ "$#" -ne 1 ] || [ -z "${RELEASE_ASSETS_JSON:-}" ]; then
    echo "error: release_asset_id requires a loaded release and one asset name" >&2
    return 2
  fi
  local name="$1"
  local count
  count=$(jq -r --arg name "$name" '[.assets[] | select(.name == $name)] | length' \
    <<<"$RELEASE_ASSETS_JSON")
  [ "$count" -eq 1 ] \
    || { echo "error: expected exactly one release asset named $name, found $count" >&2; return 1; }
  local asset_id
  asset_id=$(jq -r --arg name "$name" '.assets[] | select(.name == $name) | .id' \
    <<<"$RELEASE_ASSETS_JSON")
  case "$asset_id" in
    ''|0|0*|*[!0-9]*) echo "error: invalid asset id for $name" >&2; return 1 ;;
  esac
  printf '%s\n' "$asset_id"
}

release_asset_download() {
  if [ "$#" -ne 2 ]; then
    echo "error: release_asset_download NAME DESTINATION" >&2
    return 2
  fi
  local name="$1"
  local destination="$2"
  if ! RELEASE_ASSET_LAST_ID=$(release_asset_id "$name"); then
    return 1
  fi
  gh api -H 'Accept: application/octet-stream' \
    "repos/$RELEASE_ASSETS_REPO/releases/assets/$RELEASE_ASSET_LAST_ID" > "$destination"
  [ -s "$destination" ] \
    || { echo "error: downloaded release asset is empty: $name" >&2; return 1; }
}
