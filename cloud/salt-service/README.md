## Configuration
`salt_generator` requires a previous instalation of requirements at `requirements.txt` and the following environment variables:

 * `MONGO_USER`: mongodb username
 * `MONGO_PASS`: mongodb password corresponding to username
 * `MONGO_URL`: mongodb url
 * `KAFKA_URL`: kafka url
 * `GENERATE_SALTS`: 1 if generates different salts everytime or 0 if uses always the same salt

These environment variables can be stored at an .env file