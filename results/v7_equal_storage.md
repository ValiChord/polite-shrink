# V7 against V6 at comparable storage

24 seeds (from 600000), 200 agents. stored = total sectors held at the end (all nodes); copies = mean copies per sector at the end.

| scenario | rule | runs losing data | worst floor | mean copies at end | mean stored | mean sync | mean resizes | top decile |
|---|---|---|---|---|---|---|---|---|
| storm | V6 | 0/24 | 5 | 15.5 | 7928 | 6836 | 1876 | 78.0% |
| storm | V7 soft, R=5 | 2/24 | 0 | 5.6 | 2881 | 1122 | 1301 | 47.1% |
| storm | V7 soft, R=6 | 0/24 | 1 | 6.6 | 3380 | 1410 | 1263 | 45.4% |
| storm | V7 soft, R=7 | 0/24 | 1 | 7.7 | 3918 | 1896 | 1278 | 51.0% |
| storm | V7 soft, R=8 | 0/24 | 1 | 8.7 | 4448 | 2219 | 1264 | 52.6% |
| storm | V7 soft, R=9 | 0/24 | 2 | 9.7 | 4950 | 2717 | 1250 | 51.5% |
| churn | V6 | 0/24 | 3 | 12.4 | 6337 | 6945 | 2087 | 90.7% |
| churn | V7 soft, R=5 | 0/24 | 2 | 5.9 | 3011 | 2593 | 1371 | 79.6% |
| churn | V7 soft, R=6 | 0/24 | 3 | 6.8 | 3496 | 3103 | 1341 | 80.6% |
| churn | V7 soft, R=7 | 0/24 | 3 | 7.9 | 4024 | 3739 | 1367 | 84.0% |
| churn | V7 soft, R=8 | 0/24 | 5 | 8.8 | 4482 | 4359 | 1341 | 83.5% |
| churn | V7 soft, R=9 | 0/24 | 5 | 9.6 | 4915 | 5221 | 1330 | 84.1% |
