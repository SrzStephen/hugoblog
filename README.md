# Setup

Make sure `$HOME/.go/bin/` is in your `PATH`
```zsh
go install github.com/jmooring/hvm@latest
hvm use v0.157.0
uvx pre-commit
pre-commit install
hugo serve
```

## Detect secrets
I use yelps [detect-secrets](https://github.com/Yelp/detect-secrets) in pre-commit to avoid committing secrets.

Because lots of things look like secrets, if pre-commit complaints about things that you're sure aren't secrets,
do a secrets baseline and make sure you're happy with what's ignored.
```zsh
detect-secrets scan > .secrets.baseline
```

## Update Hugo Theme
The underlying theme [loveit](https://hugoloveit.com/) is a submodule
```zsh
git submodule update --remote
git push
```

## Observability
I use New Relic for observability, `layouts/partials/newrelic.html` injects the new relic APM header
and `layouts/partials/outbound-links.html` tracks outbound link clicks as part of the tracking.

## Analytics
I also use Google Analytics for longer term tracking, `GTAG` (Not a secret) is in `hugo.toml`.