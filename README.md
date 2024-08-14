[![.github/workflows/build-test-deploy.yml](https://github.com/bids-standard/python-validator/actions/workflows/build-test-deploy.yml/badge.svg)](https://github.com/bids-standard/python-validator/actions/workflows/build-test-deploy.yml)
[![codecov](https://codecov.io/gh/bids-standard/python-validator/graph/badge.svg?token=5iz5rfzv93)](https://codecov.io/gh/bids-standard/python-validator)
[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.3688707.svg)](https://doi.org/10.5281/zenodo.3688707)
[![PyPI version](https://badge.fury.io/py/bids-validator.svg)](https://badge.fury.io/py/bids-validator)
[![Conda version](https://img.shields.io/conda/vn/conda-forge/bids-validator)](https://anaconda.org/conda-forge/bids-validator)

# Python BIDS-Validator

This is a library of helper functions written in Python,
for use with BIDS compliant applications written in this language.

The main function determines if a file path is compliant with the BIDS specification.

## Installation

To install with pip:

```
python -m pip install bids_validator
```

To install with conda:

```
conda install bids-validator
```

## Quickstart

1. Open a Python terminal and type: `python`
1. Import the BIDS Validator package `from bids_validator import BIDSValidator`
1. Check if a file is BIDS compatible `BIDSValidator().is_bids('/relative/path/to/a/bids/file')`
1. Note, the file path must be relative to the root of the BIDS dataset, and
  a leading forward slash `/` must be added to the file path.


### Example

```Python
from bids_validator import BIDSValidator

validator = BIDSValidator()

filepaths = ["/sub-01/anat/sub-01_rec-CSD_T1w.nii.gz", "/sub-01/anat/sub-01_acq-23_rec-CSD_T1w.exe"]
for filepath in filepaths:
    print(validator.is_bids(filepath))  # will print True, and then False
```

Note, the file path must be relative to the root of the BIDS dataset, and a
leading forward slash `/` must be added to the file path.

## Acknowledgments

Many contributions to the `bids-validator` were done by members of the
BIDS community. See the
[list of contributors](https://bids-specification.readthedocs.io/en/stable/99-appendices/01-contributors.html).

A large part of the initial development of `bids-validator` was done by
[Squishymedia](https://squishymedia.com/), who are in turn financed through
different grants offered for the general development of BIDS. See the list
below.

Development and contributions were supported through the following federally
funded projects/grants:

- [BIDS Derivatives (NIMH: R24MH114705, PI: Poldrack)](https://grantome.com/grant/NIH/R24-MH114705-01)
- [OpenNeuro (NIMH: R24MH117179, PI: Poldrack)](https://grantome.com/grant/NIH/R24-MH117179-01)
- [Spokes: MEDIUM: WEST (NSF: 1760950, PI: Poldrack & Gorgolewski)](https://grantome.com/grant/NSF/IIS-1760950)
- [ReproNim](http://repronim.org) [(NIH-NIBIB P41 EB019936, PI: Kennedy)](https://projectreporter.nih.gov/project_info_description.cfm?aid=8999833)

## Maintainers and Contributors

<!-- ALL-CONTRIBUTORS-BADGE:START - Do not remove or modify this section -->

[![All Contributors](https://img.shields.io/badge/all_contributors-43-orange.svg?style=flat-square)](#contributors-)

<!-- ALL-CONTRIBUTORS-BADGE:END -->

This project follows the [all-contributors](https://github.com/all-contributors/all-contributors) specification.
Contributions of any kind are welcome!

The project is maintained by [@rwblair](https://github.com/rwblair/) with the help of many contributors listed below.
(The [emoji key](https://allcontributors.org/docs/en/emoji-key) is indicating the kind of contribution)

Please also see [Acknowledgments](#acknowledgments).

<!-- ALL-CONTRIBUTORS-LIST:START - Do not remove or modify this section -->
<!-- prettier-ignore-start -->
<!-- markdownlint-disable -->
<table>
  <tr>
    <td align="center"><a href="https://adam2392.github.io/"><img src="https://avatars.githubusercontent.com/u/3460267?v=4?s=50" width="50px;" alt=""/><br /><sub><b>Adam Li</b></sub></a><br /><a href="https://github.com/bids-standard/bids-validator/commits?author=adam2392" title="Code">💻</a> <a href="https://github.com/bids-standard/bids-validator/commits?author=adam2392" title="Tests">⚠️</a> <a href="#userTesting-adam2392" title="User Testing">📓</a> <a href="https://github.com/bids-standard/bids-validator/issues?q=author%3Aadam2392" title="Bug reports">🐛</a></td>
    <td align="center"><a href="https://github.com/agt24"><img src="https://avatars.githubusercontent.com/u/7869017?v=4?s=50" width="50px;" alt=""/><br /><sub><b>Adam Thomas</b></sub></a><br /><a href="https://github.com/bids-standard/bids-validator/commits?author=agt24" title="Documentation">📖</a></td>
    <td align="center"><a href="http://happy5214.freedynamicdns.org/"><img src="https://avatars.githubusercontent.com/u/2992751?v=4?s=50" width="50px;" alt=""/><br /><sub><b>Alexander Jones</b></sub></a><br /><a href="https://github.com/bids-standard/bids-validator/commits?author=happy5214" title="Code">💻</a> <a href="https://github.com/bids-standard/bids-validator/commits?author=happy5214" title="Tests">⚠️</a> <a href="#ideas-happy5214" title="Ideas, Planning, & Feedback">🤔</a></td>
    <td align="center"><a href="https://github.com/musicinmybrain"><img src="https://avatars.githubusercontent.com/u/6898909?v=4?s=50" width="50px;" alt=""/><br /><sub><b>Ben Beasley</b></sub></a><br /><a href="#platform-musicinmybrain" title="Packaging/porting to new platform">📦</a></td>
    <td align="center"><a href="http://chrisgorgolewski.org"><img src="https://avatars.githubusercontent.com/u/238759?v=4?s=50" width="50px;" alt=""/><br /><sub><b>Chris Gorgolewski</b></sub></a><br /><a href="https://github.com/bids-standard/bids-validator/issues?q=author%3Achrisgorgo" title="Bug reports">🐛</a> <a href="https://github.com/bids-standard/bids-validator/commits?author=chrisgorgo" title="Code">💻</a> <a href="#data-chrisgorgo" title="Data">🔣</a> <a href="https://github.com/bids-standard/bids-validator/commits?author=chrisgorgo" title="Documentation">📖</a> <a href="#example-chrisgorgo" title="Examples">💡</a> <a href="#ideas-chrisgorgo" title="Ideas, Planning, & Feedback">🤔</a> <a href="#infra-chrisgorgo" title="Infrastructure (Hosting, Build-Tools, etc)">🚇</a> <a href="#maintenance-chrisgorgo" title="Maintenance">🚧</a> <a href="#mentoring-chrisgorgo" title="Mentoring">🧑‍🏫</a> <a href="#question-chrisgorgo" title="Answering Questions">💬</a> <a href="https://github.com/bids-standard/bids-validator/pulls?q=is%3Apr+reviewed-by%3Achrisgorgo" title="Reviewed Pull Requests">👀</a> <a href="https://github.com/bids-standard/bids-validator/commits?author=chrisgorgo" title="Tests">⚠️</a> <a href="#tutorial-chrisgorgo" title="Tutorials">✅</a> <a href="#talk-chrisgorgo" title="Talks">📢</a> <a href="#userTesting-chrisgorgo" title="User Testing">📓</a></td>
    <td align="center"><a href="https://github.com/choldgraf"><img src="https://avatars.githubusercontent.com/u/1839645?v=4?s=50" width="50px;" alt=""/><br /><sub><b>Chris Holdgraf</b></sub></a><br /><a href="https://github.com/bids-standard/bids-validator/commits?author=choldgraf" title="Code">💻</a></td>
    <td align="center"><a href="https://github.com/effigies"><img src="https://avatars.githubusercontent.com/u/83442?v=4?s=50" width="50px;" alt=""/><br /><sub><b>Chris Markiewicz</b></sub></a><br /><a href="https://github.com/bids-standard/bids-validator/commits?author=effigies" title="Code">💻</a> <a href="https://github.com/bids-standard/bids-validator/commits?author=effigies" title="Tests">⚠️</a> <a href="#ideas-effigies" title="Ideas, Planning, & Feedback">🤔</a> <a href="https://github.com/bids-standard/bids-validator/issues?q=author%3Aeffigies" title="Bug reports">🐛</a> <a href="#question-effigies" title="Answering Questions">💬</a> <a href="#tool-effigies" title="Tools">🔧</a> <a href="#maintenance-effigies" title="Maintenance">🚧</a></td>
  </tr>
  <tr>
    <td align="center"><a href="https://github.com/david-nishi"><img src="https://avatars.githubusercontent.com/u/28666458?v=4?s=50" width="50px;" alt=""/><br /><sub><b>David Nishikawa</b></sub></a><br /><a href="https://github.com/bids-standard/bids-validator/commits?author=david-nishi" title="Code">💻</a> <a href="https://github.com/bids-standard/bids-validator/commits?author=david-nishi" title="Tests">⚠️</a></td>
    <td align="center"><a href="https://github.com/DimitriPapadopoulos"><img src="https://avatars.githubusercontent.com/u/3234522?v=4?s=50" width="50px;" alt=""/><br /><sub><b>Dimitri Papadopoulos Orfanos</b></sub></a><br /><a href="https://github.com/bids-standard/bids-validator/commits?author=DimitriPapadopoulos" title="Code">💻</a></td>
    <td align="center"><a href="https://duncanmmacleod.github.io/"><img src="https://avatars.githubusercontent.com/u/1618530?v=4?s=50" width="50px;" alt=""/><br /><sub><b>Duncan Macleod</b></sub></a><br /><a href="#infra-duncanmmacleod" title="Infrastructure (Hosting, Build-Tools, etc)">🚇</a></td>
    <td align="center"><a href="https://github.com/franklin-feingold"><img src="https://avatars.githubusercontent.com/u/35307458?v=4?s=50" width="50px;" alt=""/><br /><sub><b>Franklin Feingold</b></sub></a><br /><a href="https://github.com/bids-standard/bids-validator/commits?author=franklin-feingold" title="Documentation">📖</a></td>
    <td align="center"><a href="https://github.com/thinknoack"><img src="https://avatars.githubusercontent.com/u/3342083?v=4?s=50" width="50px;" alt=""/><br /><sub><b>Gregory noack</b></sub></a><br /><a href="https://github.com/bids-standard/bids-validator/commits?author=thinknoack" title="Code">💻</a> <a href="https://github.com/bids-standard/bids-validator/commits?author=thinknoack" title="Tests">⚠️</a></td>
    <td align="center"><a href="http://chymera.eu/"><img src="https://avatars.githubusercontent.com/u/950524?v=4?s=50" width="50px;" alt=""/><br /><sub><b>Horea Christian</b></sub></a><br /><a href="https://github.com/bids-standard/bids-validator/commits?author=TheChymera" title="Code">💻</a></td>
    <td align="center"><a href="https://kaczmarj.github.io/"><img src="https://avatars.githubusercontent.com/u/17690870?v=4?s=50" width="50px;" alt=""/><br /><sub><b>Jakub Kaczmarzyk</b></sub></a><br /><a href="#infra-kaczmarj" title="Infrastructure (Hosting, Build-Tools, etc)">🚇</a></td>
  </tr>
  <tr>
    <td align="center"><a href="https://github.com/jokedurnez"><img src="https://avatars.githubusercontent.com/u/7630327?v=4?s=50" width="50px;" alt=""/><br /><sub><b>Joke Durnez</b></sub></a><br /><a href="https://github.com/bids-standard/bids-validator/commits?author=jokedurnez" title="Code">💻</a></td>
    <td align="center"><a href="http://jasmainak.github.io/"><img src="https://avatars.githubusercontent.com/u/15852194?v=4?s=50" width="50px;" alt=""/><br /><sub><b>Mainak Jas</b></sub></a><br /><a href="https://github.com/bids-standard/bids-validator/commits?author=jasmainak" title="Code">💻</a> <a href="https://github.com/bids-standard/bids-validator/commits?author=jasmainak" title="Tests">⚠️</a> <a href="#ideas-jasmainak" title="Ideas, Planning, & Feedback">🤔</a> <a href="https://github.com/bids-standard/bids-validator/pulls?q=is%3Apr+reviewed-by%3Ajasmainak" title="Reviewed Pull Requests">👀</a> <a href="#userTesting-jasmainak" title="User Testing">📓</a></td>
    <td align="center"><a href="http://fair.dei.unipd.it/marco-castellaro"><img src="https://avatars.githubusercontent.com/u/5088923?v=4?s=50" width="50px;" alt=""/><br /><sub><b>Marco Castellaro</b></sub></a><br /><a href="https://github.com/bids-standard/bids-validator/commits?author=marcocastellaro" title="Code">💻</a> <a href="https://github.com/bids-standard/bids-validator/commits?author=marcocastellaro" title="Tests">⚠️</a></td>
    <td align="center"><a href="https://github.com/MaxvandenBoom"><img src="https://avatars.githubusercontent.com/u/43676624?v=4?s=50" width="50px;" alt=""/><br /><sub><b>Max</b></sub></a><br /><a href="https://github.com/bids-standard/bids-validator/commits?author=MaxvandenBoom" title="Code">💻</a> <a href="https://github.com/bids-standard/bids-validator/issues?q=author%3AMaxvandenBoom" title="Bug reports">🐛</a></td>
    <td align="center"><a href="http://psychoinformatics.de/"><img src="https://avatars.githubusercontent.com/u/136479?v=4?s=50" width="50px;" alt=""/><br /><sub><b>Michael Hanke</b></sub></a><br /><a href="https://github.com/bids-standard/bids-validator/commits?author=mih" title="Documentation">📖</a></td>
    <td align="center"><a href="https://github.com/naveau"><img src="https://avatars.githubusercontent.com/u/1488318?v=4?s=50" width="50px;" alt=""/><br /><sub><b>Mikael Naveau</b></sub></a><br /><a href="https://github.com/bids-standard/bids-validator/commits?author=naveau" title="Code">💻</a></td>
    <td align="center"><a href="https://github.com/nellh"><img src="https://avatars.githubusercontent.com/u/11369795?v=4?s=50" width="50px;" alt=""/><br /><sub><b>Nell Hardcastle</b></sub></a><br /><a href="https://github.com/bids-standard/bids-validator/commits?author=nellh" title="Code">💻</a> <a href="#ideas-nellh" title="Ideas, Planning, & Feedback">🤔</a> <a href="#infra-nellh" title="Infrastructure (Hosting, Build-Tools, etc)">🚇</a> <a href="#question-nellh" title="Answering Questions">💬</a> <a href="https://github.com/bids-standard/bids-validator/pulls?q=is%3Apr+reviewed-by%3Anellh" title="Reviewed Pull Requests">👀</a></td>
  </tr>
  <tr>
    <td align="center"><a href="https://github.com/ntraut"><img src="https://avatars.githubusercontent.com/u/22977927?v=4?s=50" width="50px;" alt=""/><br /><sub><b>Nicolas Traut</b></sub></a><br /><a href="https://github.com/bids-standard/bids-validator/commits?author=ntraut" title="Code">💻</a></td>
    <td align="center"><a href="https://www.linkedin.com/in/parul-sethi"><img src="https://avatars.githubusercontent.com/u/11822050?v=4?s=50" width="50px;" alt=""/><br /><sub><b>Parul Sethi</b></sub></a><br /><a href="https://github.com/bids-standard/bids-validator/commits?author=parulsethi" title="Code">💻</a> <a href="https://github.com/bids-standard/bids-validator/commits?author=parulsethi" title="Tests">⚠️</a></td>
    <td align="center"><a href="https://github.com/patsycle"><img src="https://avatars.githubusercontent.com/u/41481345?v=4?s=50" width="50px;" alt=""/><br /><sub><b>Patricia Clement</b></sub></a><br /><a href="https://github.com/bids-standard/bids-validator/commits?author=patsycle" title="Code">💻</a></td>
    <td align="center"><a href="https://remi-gau.github.io/"><img src="https://avatars.githubusercontent.com/u/6961185?v=4?s=50" width="50px;" alt=""/><br /><sub><b>Remi Gau</b></sub></a><br /><a href="https://github.com/bids-standard/bids-validator/commits?author=Remi-Gau" title="Code">💻</a> <a href="https://github.com/bids-standard/bids-validator/commits?author=Remi-Gau" title="Documentation">📖</a> <a href="#userTesting-Remi-Gau" title="User Testing">📓</a></td>
    <td align="center"><a href="https://hoechenberger.net/"><img src="https://avatars.githubusercontent.com/u/2046265?v=4?s=50" width="50px;" alt=""/><br /><sub><b>Richard Höchenberger</b></sub></a><br /><a href="https://github.com/bids-standard/bids-validator/commits?author=hoechenberger" title="Code">💻</a> <a href="#userTesting-hoechenberger" title="User Testing">📓</a> <a href="https://github.com/bids-standard/bids-validator/commits?author=hoechenberger" title="Tests">⚠️</a> <a href="https://github.com/bids-standard/bids-validator/issues?q=author%3Ahoechenberger" title="Bug reports">🐛</a></td>
    <td align="center"><a href="https://github.com/robertoostenveld"><img src="https://avatars.githubusercontent.com/u/899043?v=4?s=50" width="50px;" alt=""/><br /><sub><b>Robert Oostenveld</b></sub></a><br /><a href="https://github.com/bids-standard/bids-validator/commits?author=robertoostenveld" title="Code">💻</a> <a href="#ideas-robertoostenveld" title="Ideas, Planning, & Feedback">🤔</a> <a href="https://github.com/bids-standard/bids-validator/issues?q=author%3Arobertoostenveld" title="Bug reports">🐛</a> <a href="https://github.com/bids-standard/bids-validator/commits?author=robertoostenveld" title="Tests">⚠️</a></td>
    <td align="center"><a href="https://github.com/SetCodesToFire"><img src="https://avatars.githubusercontent.com/u/25459509?v=4?s=50" width="50px;" alt=""/><br /><sub><b>Rohan Goyal</b></sub></a><br /><a href="https://github.com/bids-standard/bids-validator/commits?author=SetCodesToFire" title="Code">💻</a></td>
  </tr>
  <tr>
    <td align="center"><a href="https://github.com/rwblair"><img src="https://avatars2.githubusercontent.com/u/14927911?v=4?s=50" width="50px;" alt=""/><br /><sub><b>Ross Blair</b></sub></a><br /><a href="#maintenance-rwblair" title="Maintenance">🚧</a> <a href="#ideas-rwblair" title="Ideas, Planning, & Feedback">🤔</a> <a href="https://github.com/bids-standard/bids-validator/commits?author=rwblair" title="Code">💻</a> <a href="https://github.com/bids-standard/bids-validator/issues?q=author%3Arwblair" title="Bug reports">🐛</a> <a href="#infra-rwblair" title="Infrastructure (Hosting, Build-Tools, etc)">🚇</a> <a href="#projectManagement-rwblair" title="Project Management">📆</a> <a href="#question-rwblair" title="Answering Questions">💬</a> <a href="https://github.com/bids-standard/bids-validator/pulls?q=is%3Apr+reviewed-by%3Arwblair" title="Reviewed Pull Requests">👀</a> <a href="#tool-rwblair" title="Tools">🔧</a> <a href="https://github.com/bids-standard/bids-validator/commits?author=rwblair" title="Tests">⚠️</a></td>
    <td align="center"><a href="http://www.poldracklab.org/"><img src="https://avatars.githubusercontent.com/u/871056?v=4?s=50" width="50px;" alt=""/><br /><sub><b>Russ Poldrack</b></sub></a><br /><a href="https://github.com/bids-standard/bids-validator/commits?author=poldrack" title="Code">💻</a> <a href="#financial-poldrack" title="Financial">💵</a> <a href="#fundingFinding-poldrack" title="Funding Finding">🔍</a></td>
    <td align="center"><a href="http://soichi.us/"><img src="https://avatars.githubusercontent.com/u/923896?v=4?s=50" width="50px;" alt=""/><br /><sub><b>Soichi Hayashi</b></sub></a><br /><a href="https://github.com/bids-standard/bids-validator/issues?q=author%3Asoichih" title="Bug reports">🐛</a></td>
    <td align="center"><a href="https://www.stefanappelhoff.com"><img src="https://avatars.githubusercontent.com/u/9084751?v=4?s=50" width="50px;" alt=""/><br /><sub><b>Stefan Appelhoff</b></sub></a><br /><a href="https://github.com/bids-standard/bids-validator/issues?q=author%3Asappelhoff" title="Bug reports">🐛</a> <a href="https://github.com/bids-standard/bids-validator/commits?author=sappelhoff" title="Code">💻</a> <a href="#data-sappelhoff" title="Data">🔣</a> <a href="https://github.com/bids-standard/bids-validator/commits?author=sappelhoff" title="Documentation">📖</a> <a href="#example-sappelhoff" title="Examples">💡</a> <a href="#ideas-sappelhoff" title="Ideas, Planning, & Feedback">🤔</a> <a href="#infra-sappelhoff" title="Infrastructure (Hosting, Build-Tools, etc)">🚇</a> <a href="#maintenance-sappelhoff" title="Maintenance">🚧</a> <a href="#mentoring-sappelhoff" title="Mentoring">🧑‍🏫</a> <a href="#question-sappelhoff" title="Answering Questions">💬</a> <a href="https://github.com/bids-standard/bids-validator/pulls?q=is%3Apr+reviewed-by%3Asappelhoff" title="Reviewed Pull Requests">👀</a> <a href="https://github.com/bids-standard/bids-validator/commits?author=sappelhoff" title="Tests">⚠️</a> <a href="#tutorial-sappelhoff" title="Tutorials">✅</a> <a href="#talk-sappelhoff" title="Talks">📢</a> <a href="#userTesting-sappelhoff" title="User Testing">📓</a></td>
    <td align="center"><a href="https://github.com/suyashdb"><img src="https://avatars.githubusercontent.com/u/11152799?v=4?s=50" width="50px;" alt=""/><br /><sub><b>Suyash </b></sub></a><br /><a href="https://github.com/bids-standard/bids-validator/commits?author=suyashdb" title="Code">💻</a></td>
    <td align="center"><a href="https://github.com/tsalo"><img src="https://avatars.githubusercontent.com/u/8228902?v=4?s=50" width="50px;" alt=""/><br /><sub><b>Taylor Salo</b></sub></a><br /><a href="https://github.com/bids-standard/bids-validator/commits?author=tsalo" title="Code">💻</a></td>
    <td align="center"><a href="https://github.com/olgn"><img src="https://avatars.githubusercontent.com/u/8853289?v=4?s=50" width="50px;" alt=""/><br /><sub><b>Teal Hobson-Lowther</b></sub></a><br /><a href="https://github.com/bids-standard/bids-validator/commits?author=olgn" title="Code">💻</a> <a href="https://github.com/bids-standard/bids-validator/commits?author=olgn" title="Tests">⚠️</a></td>
  </tr>
  <tr>
    <td align="center"><a href="https://github.com/riddlet"><img src="https://avatars.githubusercontent.com/u/4789331?v=4?s=50" width="50px;" alt=""/><br /><sub><b>Travis Riddle</b></sub></a><br /><a href="https://github.com/bids-standard/bids-validator/issues?q=author%3Ariddlet" title="Bug reports">🐛</a></td>
    <td align="center"><a href="https://github.com/VisLab"><img src="https://avatars.githubusercontent.com/u/1189050?v=4?s=50" width="50px;" alt=""/><br /><sub><b>VisLab</b></sub></a><br /><a href="#ideas-VisLab" title="Ideas, Planning, & Feedback">🤔</a> <a href="https://github.com/bids-standard/bids-validator/commits?author=VisLab" title="Code">💻</a></td>
    <td align="center"><a href="https://github.com/wazeerzulfikar"><img src="https://avatars.githubusercontent.com/u/15856554?v=4?s=50" width="50px;" alt=""/><br /><sub><b>Wazeer Zulfikar</b></sub></a><br /><a href="https://github.com/bids-standard/bids-validator/commits?author=wazeerzulfikar" title="Documentation">📖</a></td>
    <td align="center"><a href="https://github.com/yarikoptic"><img src="https://avatars.githubusercontent.com/u/39889?v=4?s=50" width="50px;" alt=""/><br /><sub><b>Yaroslav Halchenko</b></sub></a><br /><a href="#ideas-yarikoptic" title="Ideas, Planning, & Feedback">🤔</a> <a href="https://github.com/bids-standard/bids-validator/commits?author=yarikoptic" title="Code">💻</a> <a href="https://github.com/bids-standard/bids-validator/commits?author=yarikoptic" title="Documentation">📖</a> <a href="#userTesting-yarikoptic" title="User Testing">📓</a></td>
    <td align="center"><a href="https://github.com/constellates"><img src="https://avatars.githubusercontent.com/u/4325905?v=4?s=50" width="50px;" alt=""/><br /><sub><b>constellates</b></sub></a><br /><a href="https://github.com/bids-standard/bids-validator/commits?author=constellates" title="Code">💻</a> <a href="https://github.com/bids-standard/bids-validator/commits?author=constellates" title="Tests">⚠️</a></td>
    <td align="center"><a href="https://github.com/dewarrn1"><img src="https://avatars.githubusercontent.com/u/1322751?v=4?s=50" width="50px;" alt=""/><br /><sub><b>dewarrn1</b></sub></a><br /><a href="https://github.com/bids-standard/bids-validator/commits?author=dewarrn1" title="Code">💻</a></td>
    <td align="center"><a href="https://github.com/dkp"><img src="https://avatars.githubusercontent.com/u/965184?v=4?s=50" width="50px;" alt=""/><br /><sub><b>dkp</b></sub></a><br /><a href="https://github.com/bids-standard/bids-validator/commits?author=dkp" title="Code">💻</a></td>
  </tr>
  <tr>
    <td align="center"><a href="https://github.com/MatthewZito"><img src="https://avatars.githubusercontent.com/u/47864657?v=4?s=50" width="50px;" alt=""/><br /><sub><b>goldmund</b></sub></a><br /><a href="https://github.com/bids-standard/bids-validator/commits?author=MatthewZito" title="Code">💻</a> <a href="https://github.com/bids-standard/bids-validator/commits?author=MatthewZito" title="Tests">⚠️</a></td>
  </tr>
</table>

<!-- markdownlint-restore -->
<!-- prettier-ignore-end -->

<!-- ALL-CONTRIBUTORS-LIST:END -->
