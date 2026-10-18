resource "aws_cloudwatch_metric_alarm" "idle_cpu" {
  alarm_name          = "foc-idle-cpu"
  namespace           = "AWS/EC2"
  metric_name         = "CPUUtilization"
  statistic           = "Average"
  period              = 300
  evaluation_periods  = 6
  threshold           = var.idle_cpu_threshold_percent
  comparison_operator = "LessThanThreshold"
  treat_missing_data  = "notBreaching"
  dimensions = {
    InstanceId = aws_instance.node.id
  }
  alarm_actions = ["arn:aws:automate:${var.region}:ec2:stop"]
}

resource "aws_sns_topic" "alerts" {
  name = "foc-alerts"
}

resource "aws_sns_topic_subscription" "email" {
  topic_arn = aws_sns_topic.alerts.arn
  protocol  = "email"
  endpoint  = var.alert_email
}

resource "aws_scheduler_schedule" "nightly_stop" {
  name = "foc-nightly-stop"

  flexible_time_window {
    mode = "OFF"
  }

  schedule_expression          = var.nightly_stop_cron
  schedule_expression_timezone = "Asia/Singapore"

  target {
    arn      = "arn:aws:scheduler:::aws-sdk:ec2:stopInstances"
    role_arn = aws_iam_role.scheduler.arn
    input    = jsonencode({ InstanceIds = [aws_instance.node.id] })
  }
}

resource "aws_budgets_budget" "monthly" {
  name         = "foc-monthly"
  budget_type  = "COST"
  limit_amount = tostring(var.budget_limit_usd)
  limit_unit   = "USD"
  time_unit    = "MONTHLY"

  notification {
    threshold                  = 50
    comparison_operator        = "GREATER_THAN"
    threshold_type             = "PERCENTAGE"
    notification_type          = "ACTUAL"
    subscriber_email_addresses = [var.alert_email]
  }

  notification {
    threshold                  = 80
    comparison_operator        = "GREATER_THAN"
    threshold_type             = "PERCENTAGE"
    notification_type          = "ACTUAL"
    subscriber_email_addresses = [var.alert_email]
  }

  notification {
    threshold                  = 100
    comparison_operator        = "GREATER_THAN"
    threshold_type             = "PERCENTAGE"
    notification_type          = "ACTUAL"
    subscriber_email_addresses = [var.alert_email]
  }
}

resource "aws_budgets_budget_action" "stop" {
  budget_name        = aws_budgets_budget.monthly.name
  action_type        = "RUN_SSM_DOCUMENTS"
  approval_model     = "AUTOMATIC"
  notification_type  = "ACTUAL"
  execution_role_arn = aws_iam_role.budget_action.arn

  action_threshold {
    action_threshold_type  = "PERCENTAGE"
    action_threshold_value = 100
  }

  definition {
    ssm_action_definition {
      action_sub_type = "STOP_EC2_INSTANCES"
      region          = var.region
      instance_ids    = [aws_instance.node.id]
    }
  }

  subscriber {
    subscription_type = "EMAIL"
    address           = var.alert_email
  }
}
