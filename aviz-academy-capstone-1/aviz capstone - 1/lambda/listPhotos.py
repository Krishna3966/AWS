import json
import boto3
import logging
from botocore.exceptions import ClientError
from boto3.dynamodb.conditions import Attr
from decimal import Decimal
import os

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Initialize AWS clients with explicit region configuration
dynamodb = boto3.resource('dynamodb', region_name='ap-south-1')
s3_client = boto3.client(
    's3',
    region_name='ap-south-1',
    config=boto3.session.Config(
        signature_version='s3v4',
        s3={'addressing_style': 'virtual'}
    ),
    endpoint_url='https://s3.ap-south-1.amazonaws.com'
)

# Environment variables
TABLE_NAME = 'PhotoGallery'
BUCKET_NAME = os.environ.get('PHOTO_BUCKET_NAME')

def lambda_handler(event, context):
    """
    Enhanced listPhotos Lambda with private S3 bucket support
    """
    try:
        logger.info("List photos request received")
        
        # Validate environment variables
        if not BUCKET_NAME:
            logger.error("PHOTO_BUCKET_NAME environment variable not set")
            return create_error_response(500, "SERVER_CONFIG_ERROR", "Server configuration error")
        
        # Get user info from Cognito claims
        user_sub = event.get('requestContext', {}).get('authorizer', {}).get('claims', {}).get('sub')
        user_email = event.get('requestContext', {}).get('authorizer', {}).get('claims', {}).get('email', 'unknown')
        
        if not user_sub:
            logger.error("No user sub found in request context")
            return create_error_response(401, "UNAUTHORIZED", "User authentication required")
        
        logger.info(f"Fetching photos for user: {user_email}")
        
        # Query DynamoDB
        try:
            table = dynamodb.Table(TABLE_NAME)

            # Return only photos owned by the authenticated user.
            # Paginate so users with more than 1MB of metadata still see all their photos.
            items = []
            scan_kwargs = {'FilterExpression': Attr('userSub').eq(user_sub)}
            while True:
                response = table.scan(**scan_kwargs)
                items.extend(response.get('Items', []))
                last_key = response.get('LastEvaluatedKey')
                if not last_key:
                    break
                scan_kwargs['ExclusiveStartKey'] = last_key

            logger.info(f"Found {len(items)} photos for user {user_email}")
            
            # Convert items and generate presigned URLs
            photos = []
            for item in items:
                try:
                    s3_key = item.get('s3Key')
                    if not s3_key:
                        logger.warning(f"Photo {item.get('photoId', 'unknown')} missing s3Key")
                        continue
                    
                    # Generate presigned URL for viewing (15 minutes)
                    try:
                        presigned_url = s3_client.generate_presigned_url(
                            'get_object',
                            Params={
                                'Bucket': BUCKET_NAME,
                                'Key': s3_key
                            },
                            ExpiresIn=900  # 15 minutes
                        )
                    except ClientError as e:
                        logger.error(f"Failed to generate presigned URL for {s3_key}: {str(e)}")
                        # Skip this photo if we can't generate URL
                        continue
                    
                    photo = {
                        'photoId': item.get('photoId'),
                        'filename': item.get('filename'),
                        's3Key': s3_key,
                        'imageUrl': presigned_url,  # Private presigned URL
                        'contentType': item.get('contentType'),
                        'uploadDate': item.get('uploadDate'),
                        'userEmail': item.get('userEmail', 'unknown'),
                        'status': item.get('status', 'active')
                    }
                    
                    # Convert any Decimal values
                    for key, value in photo.items():
                        if isinstance(value, Decimal):
                            photo[key] = float(value)
                    
                    photos.append(photo)
                    
                except Exception as e:
                    logger.warning(f"Error processing photo item {item.get('photoId', 'unknown')}: {str(e)}")
                    continue
            
            # Sort by upload date (newest first)
            photos.sort(key=lambda x: x.get('uploadDate', ''), reverse=True)
            
            logger.info(f"Successfully processed {len(photos)} photos with presigned URLs")
            
            return {
                'statusCode': 200,
                'headers': {
                    'Access-Control-Allow-Origin': '*',
                    'Access-Control-Allow-Headers': 'Content-Type,Authorization',
                    'Content-Type': 'application/json'
                },
                'body': json.dumps({
                    'success': True,
                    'photos': photos,
                    'count': len(photos),
                    'message': f'Found {len(photos)} photos',
                    'urlExpiry': '15 minutes'
                })
            }
            
        except ClientError as e:
            error_code = e.response['Error']['Code']
            logger.error(f"DynamoDB error: {error_code} - {str(e)}")
            
            if error_code == 'ResourceNotFoundException':
                return create_error_response(500, "TABLE_NOT_FOUND", "Photo database not found")
            elif error_code == 'ProvisionedThroughputExceededException':
                return create_error_response(503, "DATABASE_BUSY", "Database temporarily busy, please retry")
            elif error_code == 'AccessDeniedException':
                return create_error_response(500, "DATABASE_ACCESS_DENIED", "Access denied to photo database")
            else:
                return create_error_response(500, "DATABASE_ERROR", "Database error occurred")
        
    except Exception as e:
        # Catch any unexpected errors
        logger.error(f"Unexpected error in listPhotos: {str(e)}", exc_info=True)
        return create_error_response(500, "INTERNAL_ERROR", "An unexpected error occurred")

def create_error_response(status_code, error_code, message):
    """Create standardized error response"""
    return {
        'statusCode': status_code,
        'headers': {
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Headers': 'Content-Type,Authorization',
            'Content-Type': 'application/json'
        },
        'body': json.dumps({
            'success': False,
            'error': {
                'code': error_code,
                'message': message
            },
            'photos': [],
            'count': 0
        })
    }
