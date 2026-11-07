# Photo Gallery Architecture - CloudFront + Private S3 Implementation

## Static Site Delivery (CloudFront + OAC)

The frontend is delivered over HTTPS by Amazon CloudFront. CloudFront reads the
site files from a **private** S3 bucket using **Origin Access Control (OAC)** —
the hosting bucket is never public. The app URL is the CloudFront domain
(`https://<dist-id>.cloudfront.net/`), not an S3 website endpoint.

```
┌─────────────┐  HTTPS GET /    ┌──────────────────────────────┐
│ User Browser│ ───────────────▶│  Amazon CloudFront (CDN)     │
│             │                 │  · Default root: index.html  │
│             │ ◀─ index.html ──│  · Viewer: redirect to HTTPS │
└─────────────┘                 │  · OAC (SigV4 signed origin) │
                                └───────────────┬──────────────┘
                                                │ reads (private, OAC only)
                                                ▼
                                ┌──────────────────────────────┐
                                │  S3: aviz-photo-static-web-  │
                                │      hosting  (PRIVATE)      │
                                │  index.html, logo.png        │
                                │  Block Public Access: ON     │
                                │  Policy: allow this dist only│
                                └──────────────────────────────┘
```

## System Architecture (Auth + Data Flow)

```
┌─────────────────────────────────────────────────────────────────────┐
│                            User Browser                              │
│  ┌────────────────────────────────────────────────────────────────┐ │
│  │  index.html  (served via CloudFront, see diagram above)        │ │
│  │  - Authentication UI                                           │ │
│  │  - Photo Upload Interface                                      │ │
│  │  - Photo Gallery Display                                       │ │
│  └────────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────┘
                              │
                              │ 1. Sign In Request
                              ▼
┌─────────────────────────────────────────────────────────────────────┐
│                      Amazon Cognito                                  │
│  ┌────────────────────────────────────────────────────────────────┐ │
│  │  User Pool: PhotoGalleryUsers                                  │ │
│  │  - User authentication                                         │ │
│  │  - Token generation (ID Token)                                 │ │
│  │  - Domain: aviz.auth.ap-south-1.amazoncognito.com             │ │
│  └────────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────┘
                              │
                              │ 2. Returns ID Token
                              ▼
┌─────────────────────────────────────────────────────────────────────┐
│                            User Browser                              │
│  (Stores ID Token in memory)                                        │
└─────────────────────────────────────────────────────────────────────┘
                              │
                              │ 3. API Request with Token
                              │    Header: Authorization: <id_token>
                              ▼
┌─────────────────────────────────────────────────────────────────────┐
│                      API Gateway                                     │
│  ┌────────────────────────────────────────────────────────────────┐ │
│  │  PhotoGalleryAPI (REST API)                                    │ │
│  │  ┌──────────────────────────────────────────────────────────┐ │ │
│  │  │  Cognito Authorizer                                      │ │ │
│  │  │  - Validates ID Token                                    │ │ │
│  │  │  - Token Source: "Authorization"                         │ │ │
│  │  │  - Extracts user claims (sub, email)                     │ │ │
│  │  └──────────────────────────────────────────────────────────┘ │ │
│  │                                                                  │ │
│  │  Resources:                                                      │ │
│  │  ┌─────────────────────────────────────────────────────────┐  │ │
│  │  │  GET /photos  → listPhotos Lambda                       │  │ │
│  │  │  POST /photos → uploadPhoto Lambda                      │  │ │
│  │  └─────────────────────────────────────────────────────────┘  │ │
│  └────────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────┘
                              │
                              │ 4. Invoke Lambda with user context
                              ▼
┌─────────────────────────────────────────────────────────────────────┐
│                      AWS Lambda Functions                            │
│                                                                       │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │  uploadPhoto Lambda                                          │  │
│  │  ┌────────────────────────────────────────────────────────┐ │  │
│  │  │  1. Receive filename & contentType                     │ │  │
│  │  │  2. Generate unique photoId (UUID)                     │ │  │
│  │  │  3. Create S3 presigned PUT URL (5 min expiry)         │ │  │
│  │  │  4. Save metadata to DynamoDB                          │ │  │
│  │  │  5. Return presigned URL to client                     │ │  │
│  │  └────────────────────────────────────────────────────────┘ │  │
│  │  Environment: PHOTO_BUCKET_NAME=aviz-photo-secure-data-... │  │
│  └──────────────────────────────────────────────────────────────┘  │
│                                                                       │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │  listPhotos Lambda                                           │  │
│  │  ┌────────────────────────────────────────────────────────┐ │  │
│  │  │  1. Query DynamoDB filtered by caller's userSub        │ │  │
│  │  │  2. For each of the user's photos:                     │ │  │
│  │  │     - Generate presigned GET URL (15 min expiry)       │ │  │
│  │  │  3. Return photo list with presigned URLs              │ │  │
│  │  └────────────────────────────────────────────────────────┘ │  │
│  │  Environment: PHOTO_BUCKET_NAME=aviz-photo-secure-data-... │  │
│  └──────────────────────────────────────────────────────────────┘  │
│                                                                       │
│  IAM Role: photo-gallery-lambda-role                                │
│  - AWSLambdaBasicExecutionRole                                      │
│  - AmazonDynamoDBFullAccess                                         │
│  - AmazonS3FullAccess                                               │
└─────────────────────────────────────────────────────────────────────┘
                    │                           │
                    │ 5a. Save/Query            │ 5b. Generate
                    │     metadata              │     presigned URLs
                    ▼                           ▼
┌──────────────────────────────┐  ┌──────────────────────────────────┐
│      Amazon DynamoDB         │  │         Amazon S3                │
│  ┌────────────────────────┐ │  │  ┌────────────────────────────┐ │
│  │  Table: PhotoGallery   │ │  │  │ aviz-photo-secure-data-... │ │
│  │  ┌──────────────────┐  │ │  │  │  (PRIVATE BUCKET)          │ │
│  │  │ photoId (PK)     │  │ │  │  │  ┌──────────────────────┐ │ │
│  │  │ filename         │  │ │  │  │  │ photo1.jpg           │ │ │
│  │  │ s3Key            │  │ │  │  │  │ photo2.png           │ │ │
│  │  │ contentType      │  │ │  │  │  │ photo3.gif           │ │ │
│  │  │ uploadDate       │  │ │  │  │  └──────────────────────┘ │ │
│  │  │ userSub          │  │ │  │  │                            │ │
│  │  │ userEmail        │  │ │  │  │  Block Public Access: ON   │ │
│  │  │ status           │  │ │  │  │  CORS: Enabled             │ │
│  │  └──────────────────┘  │ │  │  └────────────────────────────┘ │
│  └────────────────────────┘ │  └──────────────────────────────────┘
└──────────────────────────────┘
                                              │
                                              │ 6. Client uploads directly
                                              │    using presigned URL
                                              ▼
                                   ┌─────────────────────┐
                                   │   User Browser      │
                                   │   (Direct S3 PUT)   │
                                   └─────────────────────┘
```

## Data Flow

### Upload Flow (Detailed)

1. **User selects photo** → Browser validates file (type, size)
2. **Browser → API Gateway**: POST /photos
   - Headers: `Authorization: <id_token>`
   - Body: `{"filename": "photo.jpg", "contentType": "image/jpeg"}`
3. **API Gateway → Cognito Authorizer**: Validates token
4. **API Gateway → uploadPhoto Lambda**: Invokes with user context
5. **uploadPhoto Lambda**:
   - Generates UUID: `abc-123-def`
   - Creates S3 key: `abc-123-def.jpg`
   - Generates presigned PUT URL (expires in 5 minutes)
   - Saves to DynamoDB:
     ```json
     {
       "photoId": "abc-123-def",
       "filename": "photo.jpg",
       "s3Key": "abc-123-def.jpg",
       "contentType": "image/jpeg",
       "userSub": "cognito-user-id",
       "userEmail": "user@example.com",
       "status": "pending"
     }
     ```
   - Returns: `{"success": true, "uploadUrl": "https://s3.amazonaws.com/..."}`
6. **Browser → S3**: Direct PUT request to presigned URL with file data
7. **S3**: Stores file in private bucket
8. **Browser**: Shows success message, refreshes gallery

### List/View Flow (Detailed)

1. **Browser → API Gateway**: GET /photos
   - Headers: `Authorization: <id_token>`
2. **API Gateway → Cognito Authorizer**: Validates token
3. **API Gateway → listPhotos Lambda**: Invokes with user context
4. **listPhotos Lambda**:
   - Queries DynamoDB: scan filtered by the caller's `userSub` (paginated)
   - For each photo:
     - Generates presigned GET URL (expires in 15 minutes)
     - Example: `https://photos-sharing-aviz-data.s3.amazonaws.com/abc-123-def.jpg?X-Amz-Algorithm=...&X-Amz-Expires=900`
   - Returns:
     ```json
     {
       "success": true,
       "photos": [
         {
           "photoId": "abc-123-def",
           "filename": "photo.jpg",
           "imageUrl": "https://s3.amazonaws.com/...?presigned-params",
           "uploadDate": "2026-01-05",
           "userEmail": "user@example.com"
         }
       ],
       "urlExpiry": "15 minutes"
     }
     ```
5. **Browser**: Displays photos using presigned URLs
6. **Browser → S3**: Loads images directly from presigned URLs

## Security Model

### Authentication Layer
- **Cognito User Pool**: Manages user identities
- **ID Token**: JWT token containing user claims (sub, email, exp)
- **Token Expiry**: 1 hour (default)

### Authorization Layer
- **API Gateway Authorizer**: Validates Cognito tokens before Lambda invocation
- **Token Source**: `Authorization` header (no "Bearer" prefix)
- **User Context**: Passed to Lambda in `event.requestContext.authorizer.claims`

### Data Access Layer
- **Private S3 Bucket**: No public access, all access via presigned URLs
- **Presigned URLs**: Time-limited, signed URLs for specific operations
  - Upload: 5 minutes (PUT operation)
  - View: 15 minutes (GET operation)
- **Lambda IAM Role**: Only Lambda can generate presigned URLs

### Benefits of This Architecture
1. ✅ **No public S3 access**: Bucket is completely private
2. ✅ **Time-limited access**: URLs expire automatically
3. ✅ **User authentication**: All API calls require valid Cognito token
4. ✅ **Direct uploads**: Files don't pass through Lambda (cost-effective)
5. ✅ **Audit trail**: DynamoDB tracks all uploads with user info
6. ✅ **Scalable**: S3 and Lambda scale automatically

## Key Differences: S3 Website Hosting vs CloudFront (Current)

| Aspect | S3 Static Website (old) | CloudFront + OAC (current) |
|--------|-------------------------|----------------------------|
| Hosting bucket access | Public read | Private — readable only by CloudFront via OAC |
| Transport | HTTP (S3 website endpoint) | HTTPS at the edge (`*.cloudfront.net` cert) |
| App URL | `https://bucket.s3.region.amazonaws.com/index.html` | `https://<dist-id>.cloudfront.net/` |
| Caching / latency | None | Global CDN edge cache |
| Cache busting | N/A | CloudFront invalidation after each upload |
| Public S3 policy | Required | None (OAC service-principal policy only) |

## Configuration Summary

### CloudFront
- **Distribution**: serves the static site over HTTPS
- **Origin**: hosting bucket REST endpoint (`aviz-photo-static-web-hosting.s3.ap-south-1.amazonaws.com`)
- **Origin access**: OAC (Origin Access Control, SigV4 signed)
- **Default root object**: `index.html`
- **Viewer protocol policy**: Redirect HTTP → HTTPS
- **App URL**: `https://<dist-id>.cloudfront.net/`

### S3 Buckets
- **Hosting**: `aviz-photo-static-web-hosting` (PRIVATE — served only through CloudFront/OAC; no website hosting)
- **Data**: `aviz-photo-secure-data-hosting` (PRIVATE, presigned URLs only)

### Lambda Functions
- **uploadPhoto**: Generates presigned PUT URLs
- **listPhotos**: Generates presigned GET URLs, filtered by `userSub` (per-user isolation)
- **Environment Variable**: `PHOTO_BUCKET_NAME=aviz-photo-secure-data-hosting`
- **Timeout**: 30 seconds
- **IAM Role**: S3 + DynamoDB + CloudWatch Logs

### API Gateway
- **Name**: PhotoGalleryAPI
- **Type**: REST API
- **Stage**: prod
- **URL**: `https://xgq35x32mg.execute-api.ap-south-1.amazonaws.com/prod`
- **Authorizer**: Cognito (Token Source: "Authorization")

### Cognito
- **User Pool**: PhotoGalleryUsers
- **Domain**: `avizway.auth.ap-south-1.amazoncognito.com`
- **Client ID**: `2uuqj6jihv0obq9glvsvei72ce`
- **Grant Type**: Implicit
- **Scopes**: email, openid
- **Callback / sign-out URLs**: the CloudFront URL (`https://<dist-id>.cloudfront.net/` and `/index.html`)

### DynamoDB
- **Table**: PhotoGallery
- **Partition Key**: photoId (String)
- **Attributes**: filename, s3Key, contentType, uploadDate, userSub, userEmail, status

## Monitoring Points

1. **CloudWatch Logs**:
   - `/aws/lambda/uploadPhoto`
   - `/aws/lambda/listPhotos`

2. **CloudWatch Metrics**:
   - Lambda invocations, errors, duration
   - API Gateway 4xx/5xx errors
   - S3 request metrics

3. **Key Metrics to Watch**:
   - Lambda errors (should be 0%)
   - API Gateway 401/403 errors (authentication issues)
   - S3 4xx errors (presigned URL issues)
   - DynamoDB throttling

## Cost Optimization

- **S3**: Pay only for storage + requests (no data transfer for presigned URLs)
- **Lambda**: Pay per invocation (minimal cost for presigned URL generation)
- **API Gateway**: Pay per API call
- **DynamoDB**: On-demand pricing (pay per request)
- **Cognito**: Free tier: 50,000 MAUs

**Estimated Monthly Cost** (for 1000 photos, 10,000 views):
- S3: ~$0.50 (storage + requests)
- Lambda: ~$0.20 (invocations)
- API Gateway: ~$0.35 (API calls)
- DynamoDB: ~$0.25 (reads/writes)
- **Total**: ~$1.30/month (well within free tier for small usage)
