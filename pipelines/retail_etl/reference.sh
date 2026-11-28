REFERENCE_URL=https://github.com/adwitiyashukla/online-retail-data-profiling-and-analysis
REFERENCE_COMMIT=3035d4db2c07c2b272f723968ef0d0b6a9e6ef36

fetch_reference() {
  git init -q "$1"
  git -C "$1" fetch -q --depth 1 "$REFERENCE_URL" "$REFERENCE_COMMIT"
  git -C "$1" checkout -q FETCH_HEAD
}
