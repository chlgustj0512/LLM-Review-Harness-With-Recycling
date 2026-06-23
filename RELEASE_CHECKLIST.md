# Public release checklist

## Required before GitHub publication

- [x] Add GitHub repository URL.
- [x] Add Apache-2.0 for software source code.
- [x] Add CC-BY-4.0 for documentation and the design PDF.
- [ ] Confirm no secrets, personal paths, private logs, or model credentials are included.
- [ ] Run `python -m unittest discover -s tests`.
- [ ] Confirm 133/133 tests pass.
- [ ] Run `python -m compileall -q harness tests`.
- [ ] Create tag `v0.15.1-disclosure`.

## Required before Zenodo publication

- [ ] Connect the GitHub repository to Zenodo or create a manual software upload.
- [x] Reserve DOI `10.5281/zenodo.20814616`.
- [x] Add the DOI to `CITATION.cff`, README, and the design PDF.
- [x] Add Apache-2.0 metadata and mixed-license notes.
- [ ] Upload the source ZIP, design PDF, and `SHA256SUMS.txt`.
- [ ] In Zenodo Licenses, add both `Apache-2.0` and `CC-BY-4.0`.
- [ ] Verify title, author spelling, ORCID, version, date, and related GitHub URL.
- [ ] Publish only after the DOI-bearing files are final.
