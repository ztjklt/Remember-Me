#!/bin/bash
set -euo pipefail
ios_root="$(cd "$(dirname "$0")/.." && pwd)"
version='3.60.107.1100'
checksum='dce7688ffbf30a009bc148640131fa082f1bc91830d776d809a93ecb3b122e16'
vendor_root="$ios_root/Vendor/VolcEngineRTC"
archive_path="$(mktemp -t remember-volcengine)"
trap 'rm -f "$archive_path"' EXIT
curl --fail --location --silent --show-error \
  "https://hstob-cdn-tos.volccdn.com/volcengine/VolcEngineRTC/$version/VolcEngineRTC.zip" -o "$archive_path"
actual="$(shasum -a 256 "$archive_path" | awk '{print $1}')"
[[ "$actual" == "$checksum" ]] || { echo 'Volcengine SDK checksum mismatch' >&2; exit 1; }
mkdir -p "$vendor_root"
unzip -oq "$archive_path" 'VolcEngineRTC.xcframework/*' 'RealXBase.xcframework/*' 'RTCFFmpeg.xcframework/*' -d "$vendor_root"
