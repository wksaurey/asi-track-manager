from django.contrib import messages
from django.contrib.auth import login, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from .forms import UserRegistrationForm, UsernameChangeForm, CustomPasswordChangeForm
from .models import User


def register(request):
    if request.method == 'POST':
        form = UserRegistrationForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            next_url = request.GET.get('next', '')
            if next_url and url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()}):
                return redirect(next_url)
            return redirect('cal:calendar')
    else:
        form = UserRegistrationForm()
    return render(request, 'users/register.html', {'form': form})


@login_required
def profile(request):
    """Allow users to change their username and/or password."""
    next_url = request.GET.get('next', '')
    username_form = UsernameChangeForm(user=request.user)
    password_form = CustomPasswordChangeForm(user=request.user)

    if request.method == 'POST':
        next_url = request.POST.get('next', next_url)
        action = request.POST.get('action')

        if action == 'change_username':
            username_form = UsernameChangeForm(request.POST, user=request.user)
            if username_form.is_valid():
                request.user.username = username_form.cleaned_data['username']
                request.user.save(update_fields=['username'])
                messages.success(request, 'Username updated successfully.')
                redirect_url = reverse('users:profile')
                if next_url:
                    redirect_url += f'?next={next_url}'
                return redirect(redirect_url)

        elif action == 'change_password':
            password_form = CustomPasswordChangeForm(user=request.user, data=request.POST)
            if password_form.is_valid():
                password_form.save()
                update_session_auth_hash(request, password_form.user)
                messages.success(request, 'Password updated successfully.')
                redirect_url = reverse('users:profile')
                if next_url:
                    redirect_url += f'?next={next_url}'
                return redirect(redirect_url)

    return render(request, 'users/profile.html', {
        'username_form': username_form,
        'password_form': password_form,
        'next_url': next_url,
    })


@login_required
def user_management(request):
    """Admin-only page to view and manage users."""
    if not request.user.is_staff:
        return redirect('cal:calendar')
    users = User.objects.all().order_by('-is_superuser', '-is_developer', '-is_staff', 'username')
    return render(request, 'users/management.html', {'users': users})


@login_required
@require_POST
def toggle_admin(request, user_id):
    """Toggle a user's admin (is_staff) status. Only admins can do this."""
    if not request.user.is_staff:
        return JsonResponse({'error': 'Permission denied'}, status=403)

    target_user = get_object_or_404(User, pk=user_id)

    if target_user == request.user:
        return JsonResponse({'error': 'You cannot change your own admin status'}, status=400)

    if target_user.is_superuser and not request.user.is_superuser:
        return JsonResponse({'error': 'Only superusers can demote other superusers'}, status=403)

    target_user.is_staff = not target_user.is_staff
    target_user.save(update_fields=['is_staff'])

    return JsonResponse({
        'success': True,
        'user_id': target_user.pk,
        'username': target_user.username,
        'is_staff': target_user.is_staff,
    })


@login_required
@require_POST
def set_role(request, user_id):
    """Set a user's role. Roles are hierarchical: staff > admin > user.
    Staff sets is_developer + is_staff. Admin sets is_staff only. User clears both."""
    if not request.user.is_staff:
        return JsonResponse({'error': 'Permission denied'}, status=403)

    target_user = get_object_or_404(User, pk=user_id)
    role = request.POST.get('role', '')

    if target_user == request.user:
        return JsonResponse({'error': 'You cannot change your own role'}, status=400)

    if target_user.is_superuser and not request.user.is_superuser:
        return JsonResponse({'error': 'Only superusers can modify other superusers'}, status=403)

    if target_user.is_developer and not (request.user.is_developer or request.user.is_superuser):
        return JsonResponse({'error': 'Only staff or superusers can modify staff users'}, status=403)

    if role == 'staff' and not (request.user.is_developer or request.user.is_superuser):
        return JsonResponse({'error': 'Only staff or superusers can grant staff role'}, status=403)

    if role == 'staff':
        target_user.is_developer = True
        target_user.is_staff = True
    elif role == 'admin':
        target_user.is_developer = False
        target_user.is_staff = True
    elif role == 'user':
        target_user.is_developer = False
        target_user.is_staff = False
    else:
        return JsonResponse({'error': 'Invalid role'}, status=400)

    target_user.save(update_fields=['is_developer', 'is_staff'])

    return JsonResponse({
        'success': True,
        'user_id': target_user.pk,
        'username': target_user.username,
        'role': role,
    })


@login_required
@require_POST
def delete_user(request, user_id):
    """Delete a user account. Only admins can do this."""
    if not request.user.is_staff:
        return JsonResponse({'error': 'Permission denied'}, status=403)

    target_user = get_object_or_404(User, pk=user_id)

    if target_user == request.user:
        return JsonResponse({'error': 'You cannot delete your own account'}, status=400)

    if target_user.is_superuser and not request.user.is_superuser:
        return JsonResponse({'error': 'Only superusers can delete other superusers'}, status=403)

    username = target_user.username
    target_user.delete()

    return JsonResponse({
        'success': True,
        'username': username,
    })
