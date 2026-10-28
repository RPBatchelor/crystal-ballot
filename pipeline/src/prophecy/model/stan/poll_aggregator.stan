// State-space poll aggregator for primary votes.
//
// Latent weekly vote shares for K parties (last = Others, the reference category)
// follow a random walk on the additive-log-ratio scale, starting near the previous
// election result. Each poll observes a subset of party shares with sampling error,
// extra non-sampling error, and a pollster house effect. House effects sum to zero
// across pollsters, so the aggregate tracks the polling industry average; systematic
// industry-wide error is added downstream, calibrated from past elections.
data {
  int<lower=2> K;                     // parties incl. reference "Others" (last)
  int<lower=2> T;                     // weeks, week 1 = previous election
  int<lower=1> J;                     // pollsters
  int<lower=1> N;                     // observations (poll x party)
  array[N] int<lower=1, upper=T> week;
  array[N] int<lower=1, upper=J> pollster;
  array[N] int<lower=1, upper=K - 1> party;
  vector<lower=0, upper=100>[N] y;    // reported share (%)
  vector<lower=1>[N] n_eff;           // effective sample size (n / design effect)
  vector[K] start_share;              // prior centre for week 1 (%), sums to 100
  vector<lower=0>[K - 1] start_sd;    // prior sd for week-1 log-ratios
  // One Nation (or any party) may only be reported by some pollsters; its house
  // effects sum to zero over those pollsters alone.
  array[K - 1] int<lower=0, upper=J> J_k;                // pollsters reporting party k
  array[K - 1, J] int<lower=0, upper=J> house_slot;      // pollster -> slot (0 = none)
}
transformed data {
  vector[K - 1] alr0 = log(start_share[1:(K - 1)] / start_share[K]);
  // Flat indices into column-major share[ , 1:K-1] and house matrices.
  array[N] int share_idx;
  array[N] int house_idx;
  for (i in 1:N) {
    share_idx[i] = (party[i] - 1) * T + week[i];
    house_idx[i] = (party[i] - 1) * J + pollster[i];
  }
}
parameters {
  vector[K - 1] eta0_raw;
  matrix[T - 1, K - 1] z;             // non-centred weekly innovations
  vector<lower=0>[K - 1] sigma_walk;  // weekly random-walk sd (log-ratio)
  vector<lower=0>[K - 1] tau;         // non-sampling error (points)
  vector<lower=0>[K - 1] sigma_house; // spread of house effects (points)
  // House effects: one sum-to-zero vector per party, padded to J.
  array[K - 1] vector[J] house_raw;
}
transformed parameters {
  matrix[T, K - 1] eta;
  matrix[T, K] share;                 // %
  array[K - 1] vector[J] house;       // points; 0 for pollsters not reporting
  eta[1] = (alr0 + start_sd .* eta0_raw)';
  for (t in 2:T) eta[t] = eta[t - 1] + (sigma_walk .* z[t - 1]')';
  for (t in 1:T) share[t] = 100 * softmax(append_row(eta[t]', 0))';
  for (k in 1:(K - 1)) {
    // Centre over reporting pollsters only.
    real m = 0;
    for (j in 1:J) if (house_slot[k, j] > 0) m += house_raw[k][j];
    m /= max(J_k[k], 1);
    for (j in 1:J)
      house[k][j] = house_slot[k, j] > 0 ? sigma_house[k] * (house_raw[k][j] - m) : 0;
  }
}
model {
  eta0_raw ~ std_normal();
  to_vector(z) ~ std_normal();
  sigma_walk ~ normal(0, 0.05);
  tau ~ normal(0, 1.5);
  sigma_house ~ normal(0, 2);
  for (k in 1:(K - 1)) house_raw[k] ~ std_normal();
  {
    vector[N] p = to_vector(share[ , 1:(K - 1)])[share_idx];
    vector[(K - 1) * J] house_flat;
    for (k in 1:(K - 1)) house_flat[((k - 1) * J + 1):(k * J)] = house[k];
    y ~ normal(p + house_flat[house_idx],
               sqrt(p .* (100 - p) ./ n_eff + square(tau[party])));
  }
}
