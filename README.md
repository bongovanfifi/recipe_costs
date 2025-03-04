This was made for a small business that wanted to pay nothing for the infrastructure maintenance and wanted it ASAP. They don't care that the code is public. The DynamoDB calls are so small that it all fits easily into free tier. Note that you have to use provisioned RCUs and WCUs to qualify for free tier. Free tier goes up to a combined capacity of 25(!!!) and unless you have a truly insane number of ingredients you can easily get away with a couple read and one write.

**The security features are garbage. Don't rely on them!** I tried to go at least a little further than the basic approach shown [here](https://docs.streamlit.io/knowledge-base/deploy/authentication-without-sso) to make the password harder to brute force, but you could just [use a managed service](https://docs.streamlit.io/develop/concepts/connections/authentication) or you could [use streamlit-authenticator](https://blog.streamlit.io/streamlit-authenticator-part-1-adding-an-authentication-component-to-your-app/), which seems pretty cool.

Streamlit has recently added an experimental st.login(). I mean to transition to that once it's stable.


Your secrets.toml should look like this:

```
[connections.db]
url = "foo"

[passwords]
admin = "foo"
kitchen = "foo"


[aws]
access_key_id = "foo"
secret_access_key = "foo"
region = "foo"
``` 
You also have to set up an IAM role with put and scan permissions for DynamoDB.

With this app, I'm continuing my habit of dedicating a full day to going from nothing to an MVP. In this case there was way more work than I thought. In hindisght, maybe I should have made this a normal React app. I had not used Streamlit before this. I assumed it would help much more than it did.