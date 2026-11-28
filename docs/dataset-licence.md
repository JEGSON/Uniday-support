# Dataset source, licence and data minimisation

The optional course-data source is the UCI Machine Learning Repository dataset
*Predict Students' Dropout and Academic Success*. UCI states that the dataset is
licensed under [Creative Commons Attribution 4.0 International (CC BY 4.0)](https://creativecommons.org/licenses/by/4.0/).
It permits sharing and adaptation subject to its attribution conditions. Source and
licence information: [UCI dataset page](https://archive.ics.uci.edu/dataset/697/predict).

Reference in APA style:

Realinho, V., Vieira Martins, M., Machado, J., & Baptista, L. (2021). *Predict students'
dropout and academic success* [Data set]. UCI Machine Learning Repository.
https://doi.org/10.24432/C5MC89

In this project, `scripts/prepare_students.py` reads the UCI `Course` column and maps
course codes to labels. It generates new demonstration identifiers, names and
example-domain emails using Faker; the script does not import source names or other
source columns. These changes are an adaptation of the source's course structure,
not a real university registry or a dataset of actual student support cases. Generated
names are fictional, although a coincidental match with a real name is possible.

Raw downloads and generated records belong under Git-ignored `data/raw/` and
`data/processed/`. Other CSV files under `data/` are ignored by default; the only
explicit exception is the small, fictional `data/examples/student_registry.example.csv`
used to demonstrate the registry importer. The source's licence does not itself
establish that it is appropriate to use any particular record as personal data in this
application. Use fictional data only and consult the institution before real use.
