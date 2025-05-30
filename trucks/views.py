from django.contrib.auth.decorators import login_required, user_passes_test
from django.core.paginator import Paginator
from django.db.models import Q, Sum
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.models import User
from django.contrib.auth import authenticate, login, logout
from django.http import JsonResponse
from django.template.loader import render_to_string

from chiqim.models import Chiqim
from .models import Truck
from xarajatlar.models import Xarajat
from .forms import TruckForm


# Admin ekanligini tekshirish
def is_admin(user):
    return user.is_superuser

def login_view(request):
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        user = authenticate(request, username=username, password=password)
        if user is not None:
            login(request, user)
            messages.success(request, "Tizimga muvaffaqiyatli kirdingiz!")
            return redirect('dashboard')
        else:
            messages.error(request, "Username yoki parol noto'g'ri!")
    return render(request, 'login.html')

def logout_view(request):
    logout(request)
    messages.success(request, "Tizimdan muvaffaqiyatli chiqdingiz!")
    return redirect('login')

@login_required
@user_passes_test(is_admin)
def user_list(request):
    users = User.objects.all().order_by('username')
    context = {
        'users': users,
    }
    return render(request, 'user_list.html', context)

@login_required
@user_passes_test(is_admin)
def add_user(request):
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        email = request.POST.get('email', '')

        if not username or not password:
            error_message = "Username va parol kiritilishi shart!"
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({
                    'success': False,
                    'message': error_message,
                    'errors': {'username': 'Username kiritilishi shart', 'password': 'Parol kiritilishi shart'}
                }, status=400)
            messages.error(request, error_message)
            return render(request, 'add_user_form.html')

        if User.objects.filter(username=username).exists():
            error_message = "Bu username allaqachon mavjud!"
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({
                    'success': False,
                    'message': error_message,
                    'errors': {'username': 'Bu username allaqachon mavjud'}
                }, status=400)
            messages.error(request, error_message)
            return render(request, 'add_user_form.html')

        try:
            user = User.objects.create_user(username=username, password=password, email=email)
            user.save()
            success_message = f"Foydalanuvchi {username} muvaffaqiyatli qo'shildi!"
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({
                    'success': True,
                    'message': success_message,
                    'redirect_url': '/users/'
                })
            messages.success(request, success_message)
            return redirect('user_list')
        except Exception as e:
            error_message = f"Foydalanuvchi qo'shishda xato: {str(e)}"
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({
                    'success': False,
                    'message': error_message,
                    'errors': {'__all__': str(e)}
                }, status=400)
            messages.error(request, error_message)
            return render(request, 'add_user_form.html')

    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        html = render_to_string('add_user_form.html', request=request)
        return JsonResponse({
            'success': True,
            'html': html
        })
    return render(request, 'add_user_form.html')

@login_required
@user_passes_test(is_admin)
def edit_user(request, user_id):
    user = get_object_or_404(User, id=user_id)
    if request.method == 'POST':
        username = request.POST.get('username')
        email = request.POST.get('email', '')
        password = request.POST.get('password', '')

        if User.objects.filter(username=username).exclude(id=user_id).exists():
            messages.error(request, "Bu username allaqachon mavjud!")
            return render(request, 'edit_user_form.html', {'user': user})
        else:
            user.username = username
            user.email = email
            if password:
                user.set_password(password)
            user.save()
            messages.success(request, f"Foydalanuvchi {username} muvaffaqiyatli yangilandi!")
            return redirect('user_list')

    return render(request, 'edit_user_form.html', {'user': user})

@login_required
@user_passes_test(is_admin)
def delete_user(request, user_id):
    user = get_object_or_404(User, id=user_id)
    if request.method == 'POST':
        if user.is_superuser:
            messages.error(request, "Superuser foydalanuvchisini o'chirib bo'lmaydi!")
            return redirect('user_list')
        else:
            username = user.username
            user.delete()
            messages.success(request, f"Foydalanuvchi {username} muvaffaqiyatli o'chirildi!")
            return redirect('user_list')

    return render(request, 'confirm_user_delete.html', {'user': user})


@login_required
def dashboard(request):
    query = request.GET.get('q', '')

    # Base queryset for trucks, excluding sold trucks
    if request.user.is_superuser:
        trucks = Truck.objects.filter(sotilgan=False)
        xarajatlar = Xarajat.objects.all()
    else:
        trucks = Truck.objects.filter(user=request.user, sotilgan=False)
        xarajatlar = Xarajat.objects.filter(truck__user=request.user)

    # Apply search filtering
    if query:
        trucks = trucks.filter(
            Q(make__icontains=query) |
            Q(model__icontains=query) |
            Q(location__icontains=query) |
            Q(company__icontains=query) |
            Q(description__icontains=query) |
            Q(seriya__icontains=query)
        )

    # Paginate trucks (10 per page)
    paginator = Paginator(trucks, 10)
    page_number = request.GET.get('page')
    trucks_page = paginator.get_page(page_number)

    # Calculate aggregates
    total_price = trucks.aggregate(total=Sum('price'))['total'] or 0
    total_xarajat = xarajatlar.aggregate(total=Sum('miqdor'))['total'] or 0

    context = {
        'trucks': trucks_page,
        'total_price': total_price,
        'xarajatlar': xarajatlar,
        'total_xarajat': total_xarajat,
    }
    return render(request, 'dashboard.html', context)


@login_required
def add_truck(request):
    if request.method == 'POST':
        form = TruckForm(request.POST, request.FILES, user=request.user)
        if form.is_valid():
            truck = form.save(commit=False)
            if not request.user.is_superuser:
                truck.user = request.user
            truck.save()

            message = f"{truck.make} {truck.model} muvaffaqiyatli qo'shildi!"

            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({
                    'success': True,
                    'message': message,
                    'truck': {
                        'id': truck.id,
                        'make': truck.make,
                        'model': truck.model,
                        'year': truck.year,
                        'price': float(truck.price),
                        'location': truck.location,
                        'company': truck.company,
                        'horsepower': truck.horsepower,
                        'description': truck.description,
                        'image': truck.image.url if truck.image else None,
                        'seriya': truck.seriya,
                    },
                    'redirect_url': '/'
                })

            messages.success(request, message)
            return redirect('dashboard')
        else:
            errors = {field: errors[0] for field, errors in form.errors.items()}
            message = "Iltimos, xatolarni tuzating!"

            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({
                    'success': False,
                    'message': message,
                    'errors': errors
                }, status=400)

            messages.error(request, message)
            return render(request, 'add_truck_form.html', {'form': form})

    else:  # GET request
        form = TruckForm(user=request.user)
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            html = render_to_string('add_truck_form.html', {'form': form}, request=request)
            return JsonResponse({
                'success': True,
                'html': html
            })
        return render(request, 'add_truck_form.html', {'form': form})


@login_required
def edit_truck(request, truck_id):
    if request.user.is_superuser:
        truck = get_object_or_404(Truck, id=truck_id)
    else:
        truck = get_object_or_404(Truck, id=truck_id, user=request.user)

    if request.method == 'POST':
        form = TruckForm(request.POST, request.FILES, instance=truck, user=request.user)
        if form.is_valid():
            updated_truck = form.save(commit=False)
            if not request.user.is_superuser:
                updated_truck.user = request.user
            updated_truck.save()
            message = f"{updated_truck.make} {updated_truck.model} muvaffaqiyatli yangilandi!"

            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({
                    'success': True,
                    'message': message,
                    'truck': {
                        'id': updated_truck.id,
                        'make': updated_truck.make,
                        'model': updated_truck.model,
                        'year': updated_truck.year,
                        'price': float(updated_truck.price),
                        'location': updated_truck.location,
                        'company': updated_truck.company,
                        'horsepower': updated_truck.horsepower,
                        'description': updated_truck.description,
                        'image': updated_truck.image.url if updated_truck.image else None,
                        'documents': updated_truck.documents.url if updated_truck.documents else None,
                        'purchase_date': updated_truck.purchase_date.strftime('%Y-%m-%d') if updated_truck.purchase_date else "",
                        'created_date': updated_truck.created_date.strftime('%Y-%m-%d %H:%M') if updated_truck.created_date else "",
                        'seriya': updated_truck.seriya,
                    }
                })

            messages.success(request, message)
            return redirect('dashboard')
        else:
            print("Form errors:", form.errors)
            message = "Iltimos, xatolarni tuzating!"

            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                # Flatten the errors to match the frontend's expectation
                errors = {field: error_list[0]['message'] for field, error_list in form.errors.get_json_data().items()}
                return JsonResponse({
                    'success': False,
                    'message': message,
                    'errors': errors
                }, status=400)

            messages.error(request, message)
            return render(request, 'edit_truck_form.html', {'form': form, 'truck': truck})
    else:
        form = TruckForm(instance=truck, user=request.user)
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            html = render_to_string('edit_truck_form.html', {'form': form, 'truck': truck, 'user': request.user}, request=request)
            return JsonResponse({
                'success': True,
                'html': html
            })
        return render(request, 'edit_truck_form.html', {'form': form, 'truck': truck})

@login_required
def delete_truck(request, truck_id):
    if request.user.is_superuser:
        truck = get_object_or_404(Truck, id=truck_id)
    else:
        truck = get_object_or_404(Truck, id=truck_id, user=request.user)

    if request.method == 'POST':
        truck_name = f"{truck.make} {truck.model}"
        truck.delete()
        messages.success(request, f"{truck_name} muvaffaqiyatli o'chirildi!")
        return redirect('dashboard')
    return render(request, 'confirm_delete.html', {'truck': truck})


@login_required
def trucks_list(request):
    query = request.GET.get('q', '')

    # Base queryset for all trucks
    trucks = Truck.objects.filter(user=request.user)
    if request.user.is_superuser:
        trucks = Truck.objects.all()

    # Apply search filtering
    if query:
        trucks = trucks.filter(
            Q(make__icontains=query) |
            Q(model__icontains=query) |
            Q(location__icontains=query) |
            Q(company__icontains=query) |
            Q(description__icontains=query) |
            Q(seriya__icontains=query)
        )

    # Paginate trucks (10 per page)
    paginator = Paginator(trucks, 10)
    page_number = request.GET.get('page')
    trucks_page = paginator.get_page(page_number)

    # Prepare trucks data
    trucks_data = []
    total_price = 0
    total_xarajat = 0
    total_umumiy = 0

    for truck in trucks_page:
        xarajat_sum = Xarajat.objects.filter(truck=truck).aggregate(Sum('miqdor'))['miqdor__sum'] or 0
        umumiy_narx = truck.price + xarajat_sum
        trucks_data.append({
            'truck': truck,
            'xarajat_sum': xarajat_sum,
            'umumiy_narx': umumiy_narx,
        })
        total_price += truck.price
        total_xarajat += xarajat_sum
        total_umumiy += umumiy_narx

    context = {
        'trucks_data': trucks_data,
        'total_price': total_price,
        'total_xarajat': total_xarajat,
        'total_umumiy': total_umumiy,
        'trucks': trucks_page,  # For pagination
    }
    return render(request, 'trucks/trucks_list.html', context)