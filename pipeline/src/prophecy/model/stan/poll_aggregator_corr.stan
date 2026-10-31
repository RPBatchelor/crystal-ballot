// State-space poll aggregator for primary votes, with correlated party trends and
// drifting house effects.
//
// As poll_aggregator.stan, except:
// * the parties' weekly velocity innovations are correlated (LKJ prior on their
//   correlation), so the model can learn that a fall for one major party tends to be a
//   rise for the other;
// * each pollster's house effect may drift linearly over the cycle (methods change
//   within cycles), around its mean; drifts also sum to zero across pollsters.
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
  array[K - 1] int<lower=0, upper=J> J_k;                // pollsters reporting party k
  array[K - 1, J] int<lower=0, upper=J> house_slot;      // pollster -> slot (0 = none)
}
transformed data {
  vector[K - 1] alr0 = log(start_share[1:(K - 1)] / start_share[K]);
  array[N] int share_idx;
  array[N] int house_idx;
  vector[N] t_c;                      // week, centred and scaled to [-0.5, 0.5]
  for (i in 1:N) {
    share_idx[i] = (party[i] - 1) * T + week[i];
    house_idx[i] = (party[i] - 1) * J + pollster[i];
    t_c[i] = (week[i] - 1.0) / max(T - 1, 1) - 0.5;
  }
}
parameters {
  vector[K - 1] eta0_raw;
  matrix[K - 1, T - 1] z;             // non-centred weekly velocity innovations
  vector<lower=0>[K - 1] sigma_vel;   // weekly sd of velocity changes (log-ratio/week)
  cholesky_factor_corr[K - 1] L_vel;  // correlation of the parties' velocity changes
  real<lower=0, upper=1> phi;         // velocity damping per week
  vector<lower=0>[K - 1] tau;         // non-sampling error (points)
  vector<lower=0>[K - 1] sigma_house; // spread of house effects (points)
  vector<lower=0>[K - 1] sigma_drift; // spread of house-effect drift over the cycle (points)
  array[K - 1] vector[J] house_raw;
  array[K - 1] vector[J] drift_raw;
}
transformed parameters {
  matrix[T, K - 1] eta;
  matrix[T, K] share;                 // %
  array[K - 1] vector[J] house;       // points (mean over the cycle)
  array[K - 1] vector[J] drift;       // points, change from start to end of the cycle
  eta[1] = (alr0 + start_sd .* eta0_raw)';
  {
    vector[K - 1] vel = rep_vector(0, K - 1);
    matrix[K - 1, T - 1] innov = diag_pre_multiply(sigma_vel, L_vel) * z;
    for (t in 2:T) {
      vel = phi * vel + innov[ , t - 1];
      eta[t] = eta[t - 1] + vel';
    }
  }
  for (t in 1:T) share[t] = 100 * softmax(append_row(eta[t]', 0))';
  for (k in 1:(K - 1)) {
    real m = 0;
    real md = 0;
    for (j in 1:J) if (house_slot[k, j] > 0) { m += house_raw[k][j]; md += drift_raw[k][j]; }
    m /= max(J_k[k], 1);
    md /= max(J_k[k], 1);
    for (j in 1:J) {
      house[k][j] = house_slot[k, j] > 0 ? sigma_house[k] * (house_raw[k][j] - m) : 0;
      drift[k][j] = house_slot[k, j] > 0 ? sigma_drift[k] * (drift_raw[k][j] - md) : 0;
    }
  }
}
model {
  eta0_raw ~ std_normal();
  to_vector(z) ~ std_normal();
  sigma_vel ~ normal(0, 0.01);
  L_vel ~ lkj_corr_cholesky(4);
  phi ~ beta(8, 2);
  tau ~ normal(0, 1.5);
  sigma_house ~ normal(0, 2);
  sigma_drift ~ normal(0, 1);
  for (k in 1:(K - 1)) {
    house_raw[k] ~ std_normal();
    drift_raw[k] ~ std_normal();
  }
  {
    vector[N] p = to_vector(share[ , 1:(K - 1)])[share_idx];
    vector[(K - 1) * J] house_flat;
    vector[(K - 1) * J] drift_flat;
    for (k in 1:(K - 1)) {
      house_flat[((k - 1) * J + 1):(k * J)] = house[k];
      drift_flat[((k - 1) * J + 1):(k * J)] = drift[k];
    }
    y ~ normal(p + house_flat[house_idx] + drift_flat[house_idx] .* t_c,
               sqrt(p .* (100 - p) ./ n_eff + square(tau[party])));
  }
}
generated quantities {
  corr_matrix[K - 1] Omega_vel = multiply_lower_tri_self_transpose(L_vel);
}
