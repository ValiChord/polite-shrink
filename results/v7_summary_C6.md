# V7 (V6 floor + StaleCap ceiling) in the simulator

24 fresh seeds per scenario (from 600000), 200 agents, R = 5, C = 6. Means over seeds. loss = sector-ticks with no copy; exposure = sector-ticks below R; sync = sectors fetched in total; top decile = share of storage held by the 10% largest nodes.

| scenario | arm | runs losing data | worst floor | mean exposure | mean sync | mean resizes | mean settle | mean copies at end | sectors over C at end | top decile | grows withdrawn | ceiling refusals |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| activation | V6 | 0/24 | 5 | 0 | 5302 | 1644 | 855 (0 never) | 28.96 | 478 | 68.8% | 0 | 0 |
| activation | V6+alongside | 0/24 | 5 | 0 | 11463 | 2417 | 1361 (1 never) | 8.02 | 250 | 92.0% | 0 | 0 |
| activation | V7 soft | 0/24 | 5 | 0 | 146 | 1259 | 768 (0 never) | 5.67 | 32 | 35.0% | 133 | 0 |
| activation | V7 hard | 0/24 | 5 | 0 | 1 | 1231 | 766 (0 never) | 5.58 | 23 | 31.2% | 130 | 4 |
| activation | V7 soft+multiwait | 0/24 | 5 | 0 | 129 | 1231 | 760 (0 never) | 5.55 | 21 | 30.9% | 122 | 0 |
| storm | V6 | 0/24 | 5 | 0 | 6836 | 1876 | 66 (0 never) | 15.48 | 349 | 78.0% | 0 | 0 |
| storm | V6+alongside | 0/24 | 2 | 8809 | 16726 | 2863 | 286 (0 never) | 7.12 | 190 | 91.8% | 0 | 0 |
| storm | V7 soft | 2/24 | 0 | 33265 | 1122 | 1301 | 0 (0 never) | 5.63 | 27 | 47.1% | 307 | 0 |
| storm | V7 hard | 4/24 | 0 | 445764 | 174 | 1231 | 0 (0 never) | 4.22 | 3 | 32.2% | 1975 | 1043 |
| storm | V7 soft+multiwait | 4/24 | 0 | 35653 | 1140 | 1266 | 0 (0 never) | 5.55 | 18 | 41.9% | 301 | 0 |
| flashcrowd | V6 | 0/24 | 5 | 0 | 7665 | 2278 | 113 (2 never) | 20.59 | 404 | 85.1% | 0 | 0 |
| flashcrowd | V6+alongside | 0/24 | 5 | 0 | 16301 | 3011 | 243 (2 never) | 8.00 | 282 | 91.5% | 0 | 0 |
| flashcrowd | V7 soft | 0/24 | 5 | 0 | 146 | 1264 | 0 (0 never) | 5.89 | 91 | 46.4% | 134 | 0 |
| flashcrowd | V7 hard | 0/24 | 5 | 0 | 1 | 1236 | 0 (0 never) | 5.80 | 76 | 42.9% | 132 | 4 |
| flashcrowd | V7 soft+multiwait | 0/24 | 5 | 0 | 129 | 1236 | 0 (0 never) | 5.77 | 70 | 42.7% | 122 | 0 |
| churn | V6 | 0/24 | 3 | 2359 | 6945 | 2087 | 56 (0 never) | 12.38 | 388 | 90.7% | 0 | 0 |
| churn | V6+alongside | 0/24 | 3 | 10009 | 17420 | 3113 | 486 (3 never) | 7.06 | 265 | 92.4% | 0 | 0 |
| churn | V7 soft | 0/24 | 2 | 44172 | 2593 | 1371 | 0 (0 never) | 5.88 | 114 | 79.6% | 653 | 0 |
| churn | V7 hard | 8/24 | 0 | 478164 | 327 | 1232 | 0 (0 never) | 3.56 | 2 | 44.8% | 2932 | 1164 |
| churn | V7 soft+multiwait | 0/24 | 2 | 46337 | 2588 | 1359 | 0 (0 never) | 5.73 | 96 | 78.5% | 663 | 0 |
