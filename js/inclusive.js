// Races Mark has identified as inclusive. Hand-maintained — the daily data
// refresh never touches this file.
const INCLUSIVE = {
  // Every race whose name contains one of these words (case-insensitive),
  // so a whole series is covered, including races posted later.
  seriesNames: ["PMCX"],
  // Individual races by BikeReg event ID: the number in the race's BikeReg
  // link, e.g. 75734 for https://www.bikereg.com/75734.
  eventIds: [],
};
