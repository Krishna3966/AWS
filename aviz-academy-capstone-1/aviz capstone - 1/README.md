# Secure Photo Gallery - AWS Serverless Application

A serverless photo gallery application using AWS services with private S3 bucket storage and Cognito authentication.

## 🎯 Project Overview

This application demonstrates a secure, scalable photo gallery using:
- **Amazon Cognito** for user authentication
- **API Gateway** with Cognito authorizer for secure API access
- **AWS Lambda** for serverless backend logic
- **Amazon S3** for private photo storage with presigned URLs
- **DynamoDB** for photo metadata storage
- **Static website hosting** on S3

## 🏗️ Architecture

```
User Browser → Cognito (Auth) → API Gateway (Authorizer) → Lambda → S3 (Private) + DynamoDB
```

See [ARCHITECTURE.md](ARCHITECTURE.md) for detailed architecture diagrams and data flows.

## 🔧 AWS Resources

### Account Information
- **AWS Account**: 982424467695
- **Region**: ap-south-1 (Mumbai)

### Resources
- **S3 Buckets**:
  - `photos-sharing-aviz-data` (Private - photo storage)
  - `photos-sharing-aviz-hosting` (Public - website hosting)
- **Lambda Functions**:
  - `uploadPhoto` - Generates presigned upload URLs
  - `listPhotos` - Lists photos with presigned view URLs
- **API Gateway**: `PhotoGalleryAPI`
  - URL: `https://svonqtpij8.execute-api.ap-south-1.amazonaws.com/prod`
- **Cognito User Pool**: `PhotoGalleryUsers`
  - Domain: `aviz.auth.ap-south-1.amazoncognito.com`
  - Client ID: `5adlqnvavjttjr9rhoe3sb650c`
- **DynamoDB Table**: `PhotoGallery`

## 🚀 Quick Start

### Prerequisites
- AWS CLI installed and configured
- AWS account with appropriate permissions
- Bash shell (macOS/Linux)

### 1. Verify Setup
```bash
./test-setup.sh
```
This script checks if all AWS resources are properly configured.

### 2. Deploy Application
```bash
./deploy.sh
```
This script:
- Updates Lambda functions with latest code
- Sets required environment variables
- Uploads frontend files to S3
- Verifies configuration

### 3. Access Application
Open in browser:
```
https://photos-sharing-aviz-hosting.s3.ap-south-1.amazonaws.com/index.html
```

## 📋 Manual Configuration Required

After running the deployment script, you need to verify these settings in AWS Console:

### API Gateway Authorizer
1. Go to API Gateway → PhotoGalleryAPI → Authorizers
2. Verify Token Source is set to: `Authorization` (NOT "Bearer Authorization")
3. If changed, redeploy API to `prod` stage

### Lambda Environment Variables
Both Lambda functions need this environment variable:
- **Key**: `PHOTO_BUCKET_NAME`
- **Value**: `photos-sharing-aviz-data`

The deploy script sets this automatically, but verify in Lambda console if issues occur.

## 🐛 Troubleshooting

### Common Issues

**Problem**: Upload fails with 401 Unauthorized
- **Solution**: Check [CRITICAL_FIX.md](CRITICAL_FIX.md) - Authorization header format issue

**Problem**: "PHOTO_BUCKET_NAME environment variable not set"
- **Solution**: Run `./deploy.sh` or manually set in Lambda console

**Problem**: Images don't load in gallery
- **Solution**: Check Lambda logs in CloudWatch, verify S3 permissions

**Problem**: CORS errors in browser
- **Solution**: Add CORS configuration to data bucket (see DEPLOYMENT_CHECKLIST.md)

### Debug Resources
- **Lambda Logs**: CloudWatch → `/aws/lambda/uploadPhoto` and `/aws/lambda/listPhotos`
- **Browser Console**: F12 → Console tab for frontend errors
- **Network Tab**: F12 → Network tab to inspect API calls

See [DEPLOYMENT_CHECKLIST.md](DEPLOYMENT_CHECKLIST.md) for comprehensive troubleshooting guide.

## 📁 Project Structure

```
.
├── lambda/
│   ├── uploadPhoto.py      # Lambda function for photo upload
│   └── listPhotos.py       # Lambda function for listing photos
├── s3/
│   ├── index.html          # Frontend application
│   ├── logo.png            # Application logo
│   └── s3.txt              # S3 configuration notes
├── working public/         # Reference implementation (public bucket)
│   ├── lambda/
│   └── s3/
├── deploy.sh               # Automated deployment script
├── test-setup.sh           # Setup verification script
├── ARCHITECTURE.md         # Detailed architecture documentation
├── CRITICAL_FIX.md         # Critical authorization fix documentation
├── DEPLOYMENT_CHECKLIST.md # Comprehensive deployment guide
├── Instructions.txt        # Original setup instructions
└── README.md               # This file
```

## 🔐 Security Features

### Private S3 Bucket Implementation
- ✅ S3 bucket has public access blocked
- ✅ All access via time-limited presigned URLs
- ✅ Upload URLs expire in 5 minutes
- ✅ View URLs expire in 15 minutes
- ✅ Cognito authentication required for all operations
- ✅ API Gateway authorizer validates tokens
- ✅ User context tracked in DynamoDB

### Authentication Flow
1. User signs in via Cognito hosted UI
2. Cognito returns ID token (JWT)
3. Frontend sends token in Authorization header
4. API Gateway validates token with Cognito
5. Lambda receives validated user context
6. Lambda generates presigned URLs for S3 access

## 🔄 Workflow

### Upload Photo
1. User selects photo file
2. Frontend requests presigned upload URL from API
3. Lambda generates presigned PUT URL (5 min expiry)
4. Lambda saves metadata to DynamoDB
5. Frontend uploads directly to S3 using presigned URL
6. Success message displayed

### View Photos
1. Frontend requests photo list from API
2. Lambda queries DynamoDB for photo metadata
3. Lambda generates presigned GET URLs (15 min expiry)
4. Frontend displays photos using presigned URLs
5. Browser loads images directly from S3

## 📊 Monitoring

### CloudWatch Logs
- `/aws/lambda/uploadPhoto` - Upload function logs
- `/aws/lambda/listPhotos` - List function logs

### Key Metrics
- Lambda invocation count and errors
- API Gateway 4xx/5xx errors
- S3 request metrics
- DynamoDB read/write capacity

### Recommended Alarms
- Lambda error rate > 1%
- API Gateway 5xx errors > 5
- DynamoDB throttling events

## 💰 Cost Estimate

For typical usage (1000 photos, 10,000 views/month):
- **S3**: ~$0.50 (storage + requests)
- **Lambda**: ~$0.20 (invocations)
- **API Gateway**: ~$0.35 (API calls)
- **DynamoDB**: ~$0.25 (reads/writes)
- **Cognito**: Free (under 50,000 MAUs)
- **Total**: ~$1.30/month

Most components are within AWS Free Tier for small usage.

## 🛠️ Development

### Local Testing
1. Use `http://localhost:5500/index.html` or `http://localhost:8080/index.html`
2. These URLs are configured in Cognito callback URLs
3. Use Live Server extension in VS Code for local development

### Testing Lambda Functions
```bash
# Test uploadPhoto
aws lambda invoke \
  --function-name uploadPhoto \
  --payload '{"body":"{\"filename\":\"test.jpg\",\"contentType\":\"image/jpeg\"}"}' \
  --region ap-south-1 \
  response.json

# Test listPhotos
aws lambda invoke \
  --function-name listPhotos \
  --region ap-south-1 \
  response.json
```

### Updating Code
1. Modify Lambda functions in `lambda/` directory
2. Update frontend in `s3/index.html`
3. Run `./deploy.sh` to deploy changes
4. Clear browser cache and test

## 📚 Documentation

- **[ARCHITECTURE.md](ARCHITECTURE.md)** - Detailed system architecture and data flows
- **[CRITICAL_FIX.md](CRITICAL_FIX.md)** - Authorization header fix and critical issues
- **[DEPLOYMENT_CHECKLIST.md](DEPLOYMENT_CHECKLIST.md)** - Complete deployment and troubleshooting guide
- **[Instructions.txt](Instructions.txt)** - Original setup instructions

## 🔗 Useful Links

- [AWS Lambda Documentation](https://docs.aws.amazon.com/lambda/)
- [API Gateway with Cognito](https://docs.aws.amazon.com/apigateway/latest/developerguide/apigateway-integrate-with-cognito.html)
- [S3 Presigned URLs](https://docs.aws.amazon.com/AmazonS3/latest/userguide/PresignedUrlUploadObject.html)
- [Cognito Authentication](https://docs.aws.amazon.com/cognito/latest/developerguide/authentication-flow.html)

## 🤝 Support

For issues or questions:
1. Check [CRITICAL_FIX.md](CRITICAL_FIX.md) for common problems
2. Review [DEPLOYMENT_CHECKLIST.md](DEPLOYMENT_CHECKLIST.md) troubleshooting section
3. Check CloudWatch logs for detailed error messages
4. Verify all AWS resources are properly configured using `./test-setup.sh`

## 📝 License

This is a demonstration project for educational purposes.

---

