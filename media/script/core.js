$(function () {
    $('#login-link').click(function(e) {
        e.preventDefault();
        var href = $(this).attr('href');
        if (href[0] == '/') {
            $.post(href,{},function(d,s,x) {
                window.location.reload();
            })
        } else {
            $(href).toggle();
        }
    });
    $("#login-form-pop button").click(function(e) {
        var form = $("#login-form-pop form");
        e.preventDefault();
        $.post(form.attr('action'),form.serialize(),function(data,status,xhr) {
            $('.loginmsg').hide();
            if (status == 'success') {
                window.location.reload();
            } else {
                alert(data);
            }
            $("#login-form-pop").toggle();
        }).error(function(data,status,xhr) {
            if (status == 'error') {
                $('.loginmsg').text('Invalid login').slideDown();
            }
        });
    })
    {
        var quicksearch = $('#quicksearch');
        function nixSearchLabel() {
            quicksearch.find('label').remove();
            quicksearch.find('input').focus();
            quicksearch.unbind('keypress',nixSearchLabel);
        }
        quicksearch.find('label').click(nixSearchLabel);
        quicksearch.keypress(nixSearchLabel);
        quicksearch.keypress(nixSearchLabel);
    }
    {
        var menus = $('#sitenav li a');
        function enableMenu(rel) {
            menus.addClass('hide');
            var active;
            if (typeof(rel) == 'undefined') {
                active = $('#top-crossbar a.active_nav');
                if (active.length) {
                    rel = active.eq(0).closest('li').attr('rel');
                } else {
                    rel = null;
                }
            }
            if (rel) {
                menus.closest('ul').find('[rel=' + rel + ']').removeClass('hide');
            }
        }
        function menu(rel) {
            $('#top-crossbar li[rel=' + rel + ']').mouseover(function() {
                enableMenu(rel);
            });
        }
        menu('category');
        menu('search');
        enableMenu();
    }
    
    $('.noi').click('click',function(ev) {
        alert('Coming Soon...');
        ev.stopEvent();
    });
    
    $(document).ajaxSend(function(event, xhr, settings) {
        xhr.setRequestHeader("X-CSRFToken", getCookie('csrftoken')); 
    });
    Ext.Ajax.on('beforerequest', function(conn, opts) {
        if (typeof opts.defaultHeaders == 'undefined') {
            opts.defaultHeaders = {};
        }
        opts.defaultHeaders['X-CSRFToken'] = Ext.util.Cookies.get('csrftoken');
    });
});

function getCookie(name) {
    var cookieValue = null;
    if (document.cookie && document.cookie != '') {
        var cookies = document.cookie.split(';');
        for (var i = 0; i < cookies.length; i++) {
            var cookie = jQuery.trim(cookies[i]);
            // Does this cookie string begin with the name we want?
            if (cookie.substring(0, name.length + 1) == (name + '=')) {
                cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                break;
            }
        }
    }
    return cookieValue;
}