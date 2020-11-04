function hidden_selector(elem) {

    // Hide or show the title, voting buttons, and content
    // when working with inplace forms.

    var title = ".post >  .title";
    var voting = ".post > .body > .voting";
    var content = ".post > .body > .content > .inplace";

    // Concatenate the final selector
    var selector = "{0},{1},{2}".format(title, voting, content);
    if (elem) {
        return elem.closest(selector)
    } else return $(selector)

}

function create_comment() {

    // Get the fields to submit
    var elem = $("#new-content");
    var parent = elem.closest('.post');
    var uid = parent.data("value");

    var content = $('#wmd-input');
    var cap_response = captcha();


    $.ajax('/ajax/comment/create/',
        {
            type: 'POST',
            dataType: 'json',
            ContentType: 'html',
            traditional: true,
            data: {
                'content': content.val(),
                'parent': uid,
                'recaptcha_response': cap_response,
            },
            success: function (data) {
                if (data.status === 'error') {
                    popup_message(parent, data.msg, data.status, 3000);
                    popup_message(elem, data.msg, data.status, 3000);
                } else {
                    // Redirect to the new post view.
                    window.location = data.redirect;
                    window.location.reload();
                }
            },
            error: function (xhr, status, text) {
                error_message(elem, xhr, status, text)
            }
        })
}

function cancel_inplace() {

    // Find the inplace element
    var inplace = $('#new-content');

    //if (inplace.length){}
    // Remove inplace item
    inplace.remove();

    // Find the hidden items
    var hidden = hidden_selector();

    // Show hidden items.
    hidden.each(function () {
        var is_hidden = $(this).is(':hidden');
        //
        if (is_hidden) {
            //alert($(this).attr('class'));
            hidden.show();
        }

    });


}


function prepare_inplace(content) {

    var post = content.closest(".post");

    // Get the current inplace items set to be replaced.
    var container = content.closest(".post > .body > .content > .inplace");

    // Any previously open inplace form gets closed.
    cancel_inplace(post);
    $('#modpanel').remove();

    return container

}

function activate_inplace(current, form, hide, elem) {

    current.hide();
    current.html(form);
    current.show(100).find('textarea').focus();

    //var preview = $('#preview');
    current.find('pre').addClass('language-python');
    current.find('code').addClass('language-bash');

    if (hide) {
        //alert(hide);
        var to_hide = hidden_selector(elem);
        to_hide.hide();
    }


}


function inplace_form(elem, add_comment) {

    add_comment = add_comment || false;
    // Hiding the parent comment is dependent on whether a comment is being added
    var hide_containter = !add_comment;
    var post = elem.closest(".post");
    var uid = post.data("value");
    var url = '/inplace/form/';

    // Prepare the container
    var container = prepare_inplace(elem);
    var current = $('<div id="new-content"></div>');
    container.after(current);

    // Prepare the request data
    var input = {'uid': uid};
    if (add_comment) {
        input['add_comment'] = 1;
    } else {
        container.dimmer('show');
    }

    $.ajax(url,
        {
            type: 'GET',
            dataType: 'json',
            ContentType: 'application/json',
            data: input,
            success: function (data) {

                if (data.status === 'error') {
                    popup_message(post, data.msg, data.status, 3000);
                    return
                }
                activate_inplace(current, data.inplace_form, hide_containter, elem);
                container.dimmer('hide');

            },
            error: function (xhr, status, text) {
                error_message(elem, xhr, status, text)
            }
        })
}


function update_post(uid, data) {

    // Current post content and title to replace
    // with returned values.
    var post = $("[data-value='{0}']".format(uid));
    var post_content = $(".post[data-value='{0}'] .editable".format(uid)).first();
    var post_title = $("[data-value='{0}'] .title".format(uid)).first();
    var post_tags =$("[data-value='{0}'] .tags".format(uid)).first();
    var post_users =$("[data-value='{0}'] .user-info".format(uid)).first();

    // Replace current post info with edited data
    post_content.html(data.html).show().focus();

    post_title.html(data.title).show();
    post_tags.html(data.tag_html).show();
    post_users.html(data.user_line).show();

    cancel_inplace(post);
    const content = document.createElement('p');
    content.textContent = post_content.text();

}


function edit_post(post) {

    var uid = post.data('value');

    var edit_url = '/ajax/edit/{0}/'.format(uid);

    // Get the element being
    var form = $('#new-content');

    // Form elements to submit.
    var title = form.find('#title');
    var content = form.find('#wmd-input');
    var type = form.find('#type').dropdown('get value');//.val();
    var tags = form.find('.tags').dropdown('get value');//.val();

    title = title.val() || '';
    if (!($.isNumeric(type))) {
        type = -1
    }
    content = content.val();

    var cap_response = captcha();

    $.ajax(edit_url,
        {
            type: 'POST',
            dataType: 'json',
            ContentType: 'application/json',
            traditional: true,
            data: {
                'content': content,
                'title': title,
                'type': type,
                'tag_val': tags,
                'recaptcha_response': cap_response
            },
            success: function (data) {
                if (data.status === 'error') {

                    popup_message(post, data.msg, data.status, 3000);
                    popup_message(form.find(".save,.create"), data.msg, data.status, 3000);
                } else {
                    // Update post with latest
                    update_post(uid, data);
                }
            },
            error: function (xhr, status, text) {
                error_message(form, xhr, status, text)
            }
        })
}


$(document).on(function () {

    // Initialize pagedown

    $('.ui.dropdown').dropdown();

    $(this).on('click', '#inplace .cancel', function () {
        var post = $(this).closest('.post');
        cancel_inplace(post);
    });

    $('#inplace #wmd-input').keyup(function (event) {

        // Submit form with CTRL-ENTER
        if (event.ctrlKey && (event.keyCode === 13 || event.keyCode === 10)) {
            var save = $('#inplace').find('.save, .create');
            save.click();
        }
    });

});