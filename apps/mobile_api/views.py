from django.db.models import Q, Sum
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.books.models import Book
from apps.readers.models import Reader
from apps.activity.models import ActivityRecord


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def profile(request):
    user = request.user

    try:
        reader = Reader.objects.get(user=user)
    except Reader.DoesNotExist:
        return Response(
            {"detail": "Kitobxon profili biriktirilmagan."},
            status=404,
        )

    points = (
        ActivityRecord.objects
        .filter(reader=reader)
        .aggregate(total=Sum("points"))["total"] or 0
    )

    return Response({
        "id": reader.id,
        "full_name": reader.full_name,
        "reader_code": reader.reader_code,
        "hemis_id": reader.hemis_id,
        "phone": reader.phone,
        "email": reader.email,
        "reader_type": reader.get_reader_type_display(),
        "status": reader.get_status_display(),
        "active_loans_count": reader.active_loans_count,
        "overdue_loans_count": reader.overdue_loans_count,
        "activity_points": points,
    })
    activity = ActivityRecord.objects.filter(reader=reader)
    points = activity.aggregate(total=Sum("points"))["total"] or 0

    return Response({
        "id": reader.id,
        "full_name": reader.full_name,
        "reader_code": reader.reader_code,
        "hemis_id": reader.hemis_id,
        "phone": reader.phone,
        "email": reader.email,
        "reader_type": reader.get_reader_type_display(),
        "status": reader.get_status_display(),
        "active_loans_count": reader.active_loans_count,
        "overdue_loans_count": reader.overdue_loans_count,
        "activity_points": points,
    })


@api_view(["GET"])
def api_status(request):
    return Response({
        "status": "ok",
        "message": "Smart Library API ishlayapti",
    })


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def book_list(request):
    books = Book.objects.select_related("author", "category").all()

    search = request.query_params.get("search", "").strip()
    if search:
        books = books.filter(
            Q(title__icontains=search)
            | Q(author__full_name__icontains=search)
            | Q(isbn__icontains=search)
            | Q(shelf_location__icontains=search)
        )

    results = []
    for book in books[:100]:
        results.append({
            "id": book.id,
            "title": book.title,
            "author": book.author.full_name,
            "category": str(book.category),
            "isbn": book.isbn,
            "publisher": book.publisher,
            "publication_year": book.publication_year,
            "total_quantity": book.total_quantity,
            "available_quantity": book.available_quantity,
            "shelf_location": book.shelf_location,
            "description": book.description,
            "is_available": book.is_available,
        })

    return Response({
        "count": len(results),
        "results": results,
    })
