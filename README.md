# Note

The theme that I use has a minor incompatability with newer versions of hugo,
while I wait for [#1008](https://github.com/dillonzq/LoveIt/pull/1008) to get merged in, stick with a known good
version of hugo.


```zsh
go install github.com/jmooring/hvm@latest
hvm use v0.145.0
```


## Detect secrets
```
detect-secrets scan > .secrets.baseline
```