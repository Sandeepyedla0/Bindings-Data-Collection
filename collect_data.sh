# Hand-picked set of languages.
# langs=("C" "C#" "C++" "Go" "Java" "JavaScript" "PHP" "Python" "Ruby" "Rust" "Scala" "TypeScript")

langs=("C++, python")

if [ ! -d TopLists ]; then
  mkdir TopLists;
fi

# Install required Python packages.
pip install -r requirements.txt

# Collect repos with at least 50 stars.
for lang in ${langs[@]}; do
  python3 gh_crawler.py $lang;
done

# Clone repositories in parallel and extract all language-specific files.
for lang in ${langs[@]}; do
  cat 'TopLists/'$lang'-top-repos.txt' | xargs -P16 -n1 -I% bash clone_repo.sh % $lang
done

# Deduplicate code files.
# python3 deduplicate.py
