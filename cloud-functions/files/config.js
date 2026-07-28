// Shared file-transfer limits. Keep the response part below the Makers
// Cloud Function body ceiling while allowing the paper endpoint to tell the
// browser exactly how to fetch a newly stored PDF without an extra HEAD trip.
export const MAX_FILE_BYTES = 20 * 1024 * 1024;
export const DOWNLOAD_PART_BYTES = 4 * 1024 * 1024;
