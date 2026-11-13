#!/bin/bash
# Rebuild everything from the raw files: database -> SQL -> results/ and charts/ -> notebook
set -euo pipefail
cd "$(dirname "$0")"
for f in campaign_descriptions.rda campaigns.rda coupon_redemptions.rda coupons.rda demographics.rda products.rda promotions.rds transactions.rds; do
  [ -s "data/raw/$f" ] || curl -sfL -o "data/raw/$f" "https://github.com/bradleyboehmke/completejourney/raw/master/data/$f"
done
python src/load_to_sqlite.py
python src/analysis.py > /dev/null
python -m nbconvert --to notebook --execute --inplace notebooks/analysis.ipynb
echo "Done. See results/findings.json and charts/."
