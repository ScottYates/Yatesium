#!/usr/bin/env bash
# Publishes the portable zip in a folder as a GitHub release.
#
#   publish_release.sh <folder with the zip> <commit> [tag]
#
# The tag defaults to "v" plus the version in the zip's file name. If a tag
# is given and differs, the zip is renamed to match it. If the release
# already exists, its zip is replaced.
#
# Needs GH_TOKEN and GITHUB_REPOSITORY in the environment.
set -euo pipefail

dir=$1
commit=$2
tag=${3:-}

zip=$(ls "$dir"/Yatesium-*-win-x64.zip | head -n 1)
version=$(basename "$zip" .zip)
version=${version#Yatesium-}
version=${version%-win-x64}

if [ -n "$tag" ] && [ "$tag" != "v$version" ]; then
  version=${tag#v}
  renamed="$dir/Yatesium-$version-win-x64.zip"
  mv "$zip" "$renamed"
  zip=$renamed
fi
tag="v$version"

sha256=$(sha256sum "$zip" | cut -d' ' -f1)
notes="Portable build for Windows x64. Extract the zip and run yatesium.exe.

Built from commit $commit.
SHA-256: $sha256"

if gh release view "$tag" --repo "$GITHUB_REPOSITORY" > /dev/null 2>&1; then
  gh release upload "$tag" "$zip" --repo "$GITHUB_REPOSITORY" --clobber
  gh release edit "$tag" --repo "$GITHUB_REPOSITORY" --notes "$notes"
else
  # The workflow token may not tag a commit whose workflow files differ from
  # the default branch. In that case the tag goes on the default branch; the
  # notes still name the commit that was built.
  gh release create "$tag" "$zip" --repo "$GITHUB_REPOSITORY" \
    --target "$commit" --title "Yatesium $version" --notes "$notes" ||
  gh release create "$tag" "$zip" --repo "$GITHUB_REPOSITORY" \
    --title "Yatesium $version" --notes "$notes"
fi
echo "Published $tag"
