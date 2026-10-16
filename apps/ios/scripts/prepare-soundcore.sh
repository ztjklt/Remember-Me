#!/bin/bash
set -euo pipefail
if [[ $# -ne 1 ]]; then
  echo 'Usage: prepare-soundcore.sh /path/to/iosFrameworkExport-v1.3.01' >&2
  exit 2
fi
sdk_root="$1"
ios_root="$(cd "$(dirname "$0")/.." && pwd)"
vendor_root="$ios_root/Vendor/Soundcore"
for relative in SoundcoreWorkAppleSDK/SoundcoreWorkAppleSDK.xcframework module_spplink_Release/module_spplinkKit.xcframework; do
  [[ -d "$sdk_root/$relative" ]] || { echo "Missing framework: $relative" >&2; exit 1; }
done
mkdir -p "$vendor_root"
for relative in SoundcoreWorkAppleSDK/SoundcoreWorkAppleSDK.xcframework module_spplink_Release/module_spplinkKit.xcframework; do
  /usr/bin/ditto "$sdk_root/$relative" "$vendor_root/$(basename "$relative")"
done
# Vendor local editor settings are not runtime resources.
find "$vendor_root" -name settings.local.json -type f -delete
xcodegen generate --spec "$ios_root/project.hardware.yml"
