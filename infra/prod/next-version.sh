#!/bin/sh
# Следующий номер выкладки (решение №65) по меткам git: v1.4 → value=1.5; меток нет → value=1.0.
set -eu
last=$(git tag --list 'v[0-9]*.[0-9]*' --sort=-v:refname | head -n 1)
case "$last" in
  "") echo "value=1.0" ;;
  *)
    last=${last#v}
    echo "value=${last%%.*}.$((${last#*.} + 1))"
    ;;
esac
