# NiftyEvent-50 Experiment Status

## Validated baseline

The benchmark in `benchmark_niftyevent50.py` uses real historical features and a purged
chronological 70/15/15 split. Preprocessing is fit only on training data. The validation
period selects macro-F1, and the test period is evaluated once.

The current test results are reported honestly as moderate/weak predictive benchmarks:

- Direction: Random Forest selected, 50.21% test accuracy, 0.3855 test macro-F1.
- Volatility: Random Forest selected, 71.31% test accuracy, 0.5626 test macro-F1.

These figures describe the implemented benchmark. They do not establish that the weak
predictive features have economic causality.

## Performance measures

Macro-F1 is the primary model-selection metric for both tasks because it gives every
direction or volatility class equal weight and is appropriate for imbalanced outcomes.
Accuracy is reported only as a context measure, since it can be dominated by the
majority class.

For the volatility task, the primary class is `"Yes"`; report its precision, recall,
F1 and average precision, because detecting a volatility spike is the minority-class
objective. Balanced accuracy and Matthews correlation coefficient are also reported
for a class-balanced and all-confusion-matrix view.

## Invalid experimental evidence

- Original-notebook random fallback features must not be used for publication claims.
- The combined notebook's top-three model table must be removed or rerun after replacing
  fallback features and feeding purged splits into model training.
- The extra ten-model script is reported separately and is not mixed into the 20-model
  table until a common purged protocol is applied.

## Publication positioning

The strongest defensible research contribution is the Indian corporate-announcement
dataset and benchmark, not highly accurate stock-direction prediction.

The release should accurately describe:

- 49 current Nifty 50 constituents plus BSE, rather than all 50 constituents.
- 10 active sectors, rather than 11 sectors.
- Financial Results, rather than earnings surprise or analyst-consensus surprise.
