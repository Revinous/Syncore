environment = "staging"
aws_region  = "us-east-1"

# Replace with your registry images before deployment.
orchestrator_image = "123456789012.dkr.ecr.us-east-1.amazonaws.com/syncore/orchestrator:staging"
web_image          = "123456789012.dkr.ecr.us-east-1.amazonaws.com/syncore/web:staging"

# Replace all placeholders before apply.
db_password       = "replace-with-secure-password"
openai_api_key    = "replace_me"
anthropic_api_key = "replace_me"
