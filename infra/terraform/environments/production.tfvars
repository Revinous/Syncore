environment = "production"
aws_region  = "us-east-1"

orchestrator_desired_count = 2
web_desired_count          = 2

# Replace with your registry images before deployment.
orchestrator_image = "123456789012.dkr.ecr.us-east-1.amazonaws.com/syncore/orchestrator:prod"
web_image          = "123456789012.dkr.ecr.us-east-1.amazonaws.com/syncore/web:prod"

# Replace all placeholders before apply.
db_password       = "replace-with-secure-password"
openai_api_key    = "replace_me"
anthropic_api_key = "replace_me"
