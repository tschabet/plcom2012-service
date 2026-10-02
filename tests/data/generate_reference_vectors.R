# Generates tests/data/reference_vectors.json from the reference implementation
# https://github.com/resplab/PLCOm2012 (tested with commit 5387abc).
# Usage: git clone https://github.com/resplab/PLCOm2012 && Rscript generate_reference_vectors.R > reference_vectors.json
# Adjust the path below if the clone is elsewhere.
source("PLCOm2012/R/plcom2012.R")
cases <- list(
 list("readme-example",62,"White",4,27,0,0,0,0,80,27,10),
 list("white-current",55,"White",2,22.5,0,0,0,1,20,35,0),
 list("black-former-copd-famhist",70,"Black",3,30.1,1,0,1,0,15,45,5),
 list("hispanic-former-cancer",66,"Hispanic",5,24,0,1,0,0,30,40,12),
 list("asian-current-famhist",58,"Asian",6,21,0,0,1,1,10,30,0),
 list("pacific-islander-all-flags",74,"Pacific Islander",1,33,1,1,1,1,40,55,0),
 list("american-indian-former",63,"American Indian",4,28,0,0,0,0,25,30,8),
 list("alaskan-native-current",60,"Alaskan Native",3,26,0,0,0,1,12,20,0),
 list("native-hawaiian-former",68,"Native Hawaiian",2,29.4,0,1,0,0,18,38,3),
 list("oldest-low-bmi",80,"White",2,19.5,1,0,1,1,5,60,0),
 list("low-risk-young",55,"White",6,25,0,0,0,0,5,10,25),
 list("heavy-smoker",64,"Black",2,31,1,0,1,1,60,45,0)
)
out <- c()
for (c in cases) {
  p <- plcom2012(age=c[[2]], race=c[[3]], education=c[[4]], bmi=c[[5]], copd=c[[6]],
    cancer_hist=c[[7]], family_hist_lung_cancer=c[[8]], smoking_status=c[[9]],
    smoking_intensity=c[[10]], duration_smoking=c[[11]], smoking_quit_time=c[[12]])$prob
  out <- c(out, sprintf('  {"name": "%s", "age": %s, "race": "%s", "education": %s, "bmi": %s, "copd": %s, "personal_cancer_history": %s, "family_history_lung_cancer": %s, "current_smoker": %s, "cigarettes_per_day": %s, "smoking_duration_years": %s, "quit_years": %s, "probability": %.15g}',
    c[[1]], c[[2]], c[[3]], c[[4]], c[[5]], ifelse(c[[6]]==1,"true","false"), ifelse(c[[7]]==1,"true","false"), ifelse(c[[8]]==1,"true","false"), ifelse(c[[9]]==1,"true","false"), c[[10]], c[[11]], c[[12]], p))
}
cat("[\n", paste(out, collapse=",\n"), "\n]\n", sep="")
