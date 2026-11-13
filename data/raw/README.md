Raw files come from the open `completejourney` package, which redistributes dunnhumby's
*The Complete Journey* (2017 release). To re-download:

```bash
for f in campaign_descriptions.rda campaigns.rda coupon_redemptions.rda coupons.rda demographics.rda products.rda promotions.rds transactions.rds; do
  curl -sfLO "https://github.com/bradleyboehmke/completejourney/raw/master/data/$f"
done
```
