# Setup


```zsh
go install github.com/jmooring/hvm@latest
hvm use v0.145.0
uvx pre-commit
pre-commit install
```

## Detect secrets
I use yelps [detect-secrets](https://github.com/Yelp/detect-secrets) in pre-commit to avoid committing secrets.

Because lots of things look like secrets, if pre-commit complains and you've checked, rebaseline with
```zsh
detect-secrets scan > .secrets.baseline
```

## Update Hugo Theme
```zsh
git submodule update --remote
git push
```