// State-space poll aggregator for primary votes and joint 2PP, with correlated party
// trends, multi-week fieldwork integration, multivariate within-poll multinomial
// covariance, and drifting ALR house effects.
functions {
  vector zero_sum_helmert(vector u) {
    int m = num_elements(u) + 1;
    vector[m] v = rep_vector(0.0, m);
    real sc = sqrt(1.0 * m / (m - 1));
    for (r in 1:(m - 1)) {
      real c = u[r] / sqrt(1.0 * r * (r + 1));
      for (i in 1:r) v[i] += c;
      v[r + 1] -= r * c;
    }
    return sc * v;
  }
}
data {
  int<lower=2> K;                     // parties: ALP, COAL, ..., OTH (last)
  int<lower=2> T;                     // weeks, week 1 = previous election
  int<lower=1> J;                     // pollsters
  int<lower=1> M;                     // number of polls
  array[M] int<lower=1, upper=T> poll_w_start;
  array[M] int<lower=1, upper=T> poll_w_end;
  array[M] int<lower=1, upper=J> poll_pollster;
  vector<lower=1>[M] poll_n_eff;
  array[M] int<lower=1, upper=K - 1> poll_m;
  array[M, K - 1] int<lower=0, upper=K - 1> poll_parties;
  array[M] vector<lower=0, upper=100>[K - 1] poll_y;
  int<lower=0> M_tpp;
  array[M_tpp] int<lower=1, upper=M> tpp_poll;
  vector<lower=0, upper=100>[M_tpp] tpp_y;
  vector<lower=0, upper=1>[K - 2] tpp_flow_prior;
  vector<lower=1>[K - 2] tpp_flow_conc;
  vector[K] start_share;              // prior centre for week 1 (%), sums to 100
  vector<lower=0>[K - 1] start_sd;    // prior sd for week-1 log-ratios
  array[K - 1] int<lower=0, upper=J> J_k;                // pollsters reporting party k
  array[K - 1, J] int<lower=0, upper=J> house_slot;      // pollster -> slot (0 = none)
}
transformed data {
  vector[K - 1] alr0 = log(start_share[1:(K - 1)] / start_share[K]);
  vector[M] t_c;
  for (i in 1:M) t_c[i] = (0.5 * (poll_w_start[i] + poll_w_end[i]) - 1.0) / max(T - 1, 1) - 0.5;
  array[K - 1] int H_pos;
  int H_free = 0;
  for (k in 1:(K - 1)) {
    H_pos[k] = H_free + 1;
    if (J_k[k] >= 2) H_free += J_k[k] - 1;
  }
}
parameters {
  vector[K - 1] eta0_raw;
  matrix[K - 1, T - 1] z;             // non-centred weekly velocity innovations
  vector<lower=0>[K - 1] sigma_vel;   // weekly sd of velocity changes (log-ratio/week)
  cholesky_factor_corr[K - 1] L_vel;  // correlation of the parties' velocity changes
  real<lower=0, upper=1> phi;         // velocity damping per week
  vector<lower=0>[K - 1] tau;         // non-sampling primary error (points)
  vector<lower=0>[K - 1] sigma_house; // spread of ALR house effects
  vector<lower=0>[K - 1] sigma_drift; // spread of ALR house-effect drift over the cycle
  vector[H_free] house_free;
  vector[H_free] drift_free;
  vector<lower=0, upper=1>[K - 2] flow_alp;
  real<lower=0> tau_tpp;
}
transformed parameters {
  matrix[T, K - 1] eta;
  matrix[T, K] share;                 // %
  array[K - 1] vector[J] house_alr;   // ALR scale (mean over the cycle)
  array[K - 1] vector[J] drift_alr;   // ALR scale (change from start to end of cycle)
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
    house_alr[k] = rep_vector(0.0, J);
    drift_alr[k] = rep_vector(0.0, J);
    if (J_k[k] >= 2) {
      vector[J_k[k]] vh = zero_sum_helmert(segment(house_free, H_pos[k], J_k[k] - 1));
      vector[J_k[k]] vd = zero_sum_helmert(segment(drift_free, H_pos[k], J_k[k] - 1));
      for (j in 1:J) {
        if (house_slot[k, j] > 0) {
          house_alr[k][j] = sigma_house[k] * vh[house_slot[k, j]];
          drift_alr[k][j] = sigma_drift[k] * vd[house_slot[k, j]];
        }
      }
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
  sigma_house ~ normal(0, 0.15);
  sigma_drift ~ normal(0, 0.08);
  house_free ~ std_normal();
  drift_free ~ std_normal();
  for (r in 1:(K - 2))
    flow_alp[r] ~ beta(tpp_flow_conc[r] * tpp_flow_prior[r],
                       tpp_flow_conc[r] * (1.0 - tpp_flow_prior[r]));
  tau_tpp ~ normal(0, 1.5);

  array[M] vector[K] mu_poll;
  for (i in 1:M) {
    int j = poll_pollster[i];
    int m = poll_m[i];
    int n_w = poll_w_end[i] - poll_w_start[i] + 1;
    vector[K - 1] eta_poll = rep_vector(0.0, K - 1);
    for (w in poll_w_start[i]:poll_w_end[i]) eta_poll += eta[w]';
    eta_poll /= n_w;
    for (k in 1:(K - 1)) eta_poll[k] += house_alr[k][j] + drift_alr[k][j] * t_c[i];
    vector[K] mu_full = 100 * softmax(append_row(eta_poll, 0));
    mu_poll[i] = mu_full;
    array[m] int idx = poll_parties[i, 1:m];
    vector[m] mu = mu_full[idx];
    vector[m] y_obs = poll_y[i, 1:m];
    matrix[m, m] Sigma;
    for (a in 1:m) {
      for (b in 1:m) {
        Sigma[a, b] = -mu[a] * mu[b] / poll_n_eff[i];
      }
      Sigma[a, a] += 100.0 * mu[a] / poll_n_eff[i] + square(tau[idx[a]]) + 1e-6;
    }
    y_obs ~ multi_normal_cholesky(mu, cholesky_decompose(Sigma));
  }
  for (q in 1:M_tpp) {
    int i = tpp_poll[q];
    real mu_tpp = mu_poll[i][1] + dot_product(flow_alp, mu_poll[i][3:K]);
    real sd_tpp = sqrt(fmax(mu_tpp * (100.0 - mu_tpp), 1.0) / poll_n_eff[i] + square(tau_tpp));
    tpp_y[q] ~ normal(mu_tpp, sd_tpp);
  }
}
generated quantities {
  corr_matrix[K - 1] Omega_vel = multiply_lower_tri_self_transpose(L_vel);
  array[K - 1] vector[J] house;
  {
    vector[K - 1] eta_ref = eta[T]';
    vector[K] base_share = share[T]';
    for (k in 1:(K - 1)) house[k] = rep_vector(0.0, J);
    for (j in 1:J) {
      vector[K - 1] eta_j = eta_ref;
      for (k in 1:(K - 1)) eta_j[k] += house_alr[k][j] + 0.5 * drift_alr[k][j];
      vector[K] s_j = 100 * softmax(append_row(eta_j, 0));
      for (k in 1:(K - 1)) {
        if (house_slot[k, j] > 0) house[k][j] = s_j[k] - base_share[k];
      }
    }
  }
}
