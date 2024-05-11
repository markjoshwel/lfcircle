# lfcircle

last.fm statistics generator for your friend circle!

- [users' guide](#users-guide)
  - [installation](#installation)
  - [command-line usage](#command-line-usage)
  - [example usage](#example-usage)

## users' guide

### installation

> [!IMPORTANT]  
> you should probably use pipx to install lfcircle.
> [read about installing it here if you don't have it already!](https://github.com/pypa/pipx?tab=readme-ov-file#install-pipx)

install lfcircle via pipx

```text
pipx install git+https://github.com/markjoshwel/lfcircle
```

### command-line usage

```text
usage: lfcircle [-h] [-H HEADER] [-t] [-l] [-a] [-f {ascii,markdown}]
                [-v] [targets ...]

last.fm statistics generator for your friend circle!

positional arguments:
  targets               users to target

options:
  -h, --help            show this help message and exit
  -H HEADER, --header HEADER
                        specify a report header, leave empty for none
  -t, --truncate-scheme
                        removes 'https://www.' in any links
  -l, --lowercase       makes everything lowercase
  -a, --all-the-links   adds links for top artists, albums and tracks
  -f {ascii,telegram}, --format {ascii,telegram}
                        output format type
  -v, --verbose         enable verbose logging
```

### example usage

```text
$ lfcircle user1 user2 user3 --header "woah statistics" --format ascii --lowercase

woah statistics
---------------

1. user2 — Σ109h; 293s/d  
   <https://last.fm/user/user2/listening-report/week>

   2053 scrobbles (#1)
   588 artists    (#1) : 椎名林檎
   826 albums     (#1) : elijah fox — wyoming (piano works)
   1128 tracks    (#1) : kero kero bonito — cinema

2. user3 — Σ41h; 91s/d  
   <https://last.fm/user/user2/listening-report/week>

   640 scrobbles (#2)
   146 artists   (#3) : louis cole
   262 albums    (#2) : mimideath — effective. power
   379 tracks    (#2) : aphex twin — syro u473t8+e [141.98][piezoluminescence mix]

3. user1 — Σ29h; 66s/d  
   <https://last.fm/user/user1/listening-report/week>

   462 scrobbles (#3)
   159 artists   (#2) : seraphine noir
   213 albums    (#3) : joywave — how do you feel now?
   261 tracks    (#3) : mili — gertrauda
```
