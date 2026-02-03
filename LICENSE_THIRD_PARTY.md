# Third-Party License Attributions

This project uses the following third-party libraries for the alignment monitoring feature.

---

## alpyca

**Purpose:** ASCOM Alpaca camera control
**License:** MIT License
**Copyright:** ASCOM Initiative
**Project:** https://github.com/ASCOMInitiative/alpyca

### MIT License

```
Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

---

## SEP (Source Extractor in Python)

**Purpose:** Star detection and centroid extraction
**License:** LGPLv3 (with BSD/MIT dual-licensing options)
**Copyright:** Kyle Barbary and contributors
**Project:** https://github.com/kbarbary/sep

### Citation

If you use SEP in a publication, please cite:

- Barbary, K. (2016). "SEP: Source Extractor as a library."
  *Journal of Open Source Software*, 1(6), 58.
  DOI: [10.21105/joss.00058](https://doi.org/10.21105/joss.00058)

- Bertin, E. & Arnouts, S. (1996). "SExtractor: Software for source extraction."
  *Astronomy and Astrophysics Supplement*, 117, 393-404.

### LGPLv3 Summary

SEP is free software: you can redistribute it and/or modify it under the terms
of the GNU Lesser General Public License as published by the Free Software
Foundation, either version 3 of the License, or (at your option) any later
version.

SEP is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY;
without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR
PURPOSE. See the GNU Lesser General Public License for more details.

Full license text: https://www.gnu.org/licenses/lgpl-3.0.html

---

## tetra3

**Purpose:** Astrometric plate solving (star pattern matching)
**License:** Apache License 2.0
**Copyright:** European Space Agency (ESA)
**Project:** https://github.com/esa/tetra3

### Apache License 2.0 Summary

Licensed under the Apache License, Version 2.0 (the "License"); you may not use
this file except in compliance with the License. You may obtain a copy of the
License at:

http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software distributed
under the License is distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR
CONDITIONS OF ANY KIND, either express or implied. See the License for the
specific language governing permissions and limitations under the License.

### Attribution

tetra3 was developed by the European Space Agency (ESA) for satellite attitude
determination using star trackers. It implements a fast lost-in-space plate
solving algorithm based on star pattern matching.

---

## Summary Table

| Library | Version | License | Use in This Project |
|---------|---------|---------|---------------------|
| alpyca | >= 3.0.0 | MIT | Alpaca camera control |
| sep | >= 1.2.0 | LGPLv3/BSD/MIT | Star detection |
| tetra3 | >= 0.1.0 | Apache 2.0 | Plate solving |

---

## Compliance Notes

This project complies with all third-party license requirements:

1. **alpyca (MIT):** Copyright notice and license preserved in source headers.

2. **SEP (LGPLv3):** This project uses SEP as a library (not modified), which is
   permitted under LGPLv3. Users can replace the SEP library with their own
   version. Citation requirements are documented above.

3. **tetra3 (Apache 2.0):** Copyright notice preserved. No modifications made to
   the library itself. NOTICE file requirements satisfied by this attribution.

---

*Last updated: 2026-02-02*
